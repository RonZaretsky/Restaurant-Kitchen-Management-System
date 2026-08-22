import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SmartChefPage } from "./SmartChefPage";

// Mocks only fetch, driving the real smartChefService hooks, matching
// TablesPage.test.tsx's established pattern.

const SUGGESTION = {
  id: 1,
  requested_by: 3,
  prompt_used: "...",
  generated_recipe: {
    name: "Roasted Zucchini Flatbread",
    ingredients: [{ name: "Zucchini", quantity: "1.2 kg" }],
    plating: "Sliced thin, served on a wooden board.",
  },
  ingredients_snapshot: [{ name: "Zucchini", unit: "kg", current_stock: "5.000" }],
  created_at: "2026-01-01T18:42:00Z",
};

function jsonResponse(status: number, body: unknown): Response {
  const text = JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(text),
    json: () => Promise.resolve(JSON.parse(text)),
  } as unknown as Response;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SmartChefPage />
    </QueryClientProvider>,
  );
}

describe("SmartChefPage", () => {
  it("shows the empty-state copy when there are no suggestions yet", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(200, []))));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No recipe suggestions yet.")).toBeInTheDocument();
  });

  it("renders a suggestion card with no Confirm/Dismiss actions and no chat panel", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(200, [SUGGESTION]))));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Roasted Zucchini Flatbread")).toBeInTheDocument();
    const expectedTimestamp = new Date(SUGGESTION.created_at).toLocaleString();
    expect(screen.getByText(`Requested by User #3 · generated ${expectedTimestamp}`)).toBeInTheDocument();
    expect(screen.getByText("Zucchini, 1.2 kg")).toBeInTheDocument();
    expect(screen.getByText("Sliced thin, served on a wooden board.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm into Dish" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /ask a follow-up/i })).not.toBeInTheDocument();
  });

  it("shows a generating indicator and disables the button while the mutation is pending", async () => {
    // Arrange: the POST never resolves during this test, keeping the mutation pending.
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit = {}) => {
        if (init.method === "POST") return new Promise(() => {});
        return Promise.resolve(jsonResponse(200, []));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("No recipe suggestions yet.");
    await user.click(screen.getByRole("button", { name: "Request suggestion" }));

    // Assert
    expect(await screen.findByText("Generating suggestion...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request suggestion" })).toBeDisabled();
  });

  it("shows the inline error message on a failed generation, not a stuck generating state", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit = {}) => {
        if (init.method === "POST") {
          return Promise.resolve(jsonResponse(502, { detail: "Couldn't generate a suggestion right now" }));
        }
        return Promise.resolve(jsonResponse(200, []));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("No recipe suggestions yet.");
    await user.click(screen.getByRole("button", { name: "Request suggestion" }));

    // Assert
    expect(await screen.findByText("Couldn't generate a suggestion right now")).toBeInTheDocument();
    expect(screen.queryByText("Generating suggestion...")).not.toBeInTheDocument();
  });

  it("includes the direction field's text in the submitted request body", async () => {
    // Arrange
    let submitted: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit = {}) => {
        if (init.method === "POST") {
          submitted = JSON.parse(String(init.body));
          return Promise.resolve(jsonResponse(201, SUGGESTION));
        }
        return Promise.resolve(jsonResponse(200, []));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("No recipe suggestions yet.");
    await user.type(screen.getByLabelText("Direction (optional)"), "something for dessert");
    await user.click(screen.getByRole("button", { name: "Request suggestion" }));

    // Assert
    await vi.waitFor(() => expect(submitted).toEqual({ direction: "something for dessert" }));
  });
});
