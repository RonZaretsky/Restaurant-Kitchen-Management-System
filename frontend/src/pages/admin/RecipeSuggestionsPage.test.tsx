import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RecipeSuggestionsPage } from "./RecipeSuggestionsPage";

// Mocks only fetch, driving the real smartChefService hooks, matching
// SmartChefPage.test.tsx's established pattern.

const navigateMock = vi.fn();
vi.mock("react-router", async () => {
  const actual = await vi.importActual<typeof import("react-router")>("react-router");
  return { ...actual, useNavigate: () => navigateMock };
});

function suggestion(overrides: Partial<Record<string, unknown>> = {}) {
  return {
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
    dismissed: false,
    confirmed_dish_id: null,
    ...overrides,
  };
}

function jsonResponse(status: number, body: unknown): Response {
  const text = JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(text),
    json: () => Promise.resolve(JSON.parse(text)),
  } as unknown as Response;
}

function stubSuggestions(suggestions: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit = {}) => {
      const path = String(url);
      if (path.includes("/dismiss")) return Promise.resolve(jsonResponse(200, suggestions[0]));
      if (path.includes("/api/smart-chef/suggestions") && (init.method ?? "GET") === "GET") {
        return Promise.resolve(jsonResponse(200, suggestions));
      }
      return Promise.reject(new Error(`unexpected request: ${path}`));
    }),
  );
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RecipeSuggestionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RecipeSuggestionsPage", () => {
  it("shows the empty-state copy when nothing is awaiting review", async () => {
    // Arrange
    stubSuggestions([]);

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No suggestions awaiting review.")).toBeInTheDocument();
  });

  it("excludes a dismissed or already-confirmed suggestion even though the raw response includes it", async () => {
    // Arrange
    stubSuggestions([
      suggestion({ id: 1, dismissed: true }),
      suggestion({ id: 2, confirmed_dish_id: 42 }),
    ]);

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No suggestions awaiting review.")).toBeInTheDocument();
  });

  it("renders a card with Confirm and Dismiss actions for a suggestion awaiting review", async () => {
    // Arrange
    stubSuggestions([suggestion()]);

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Roasted Zucchini Flatbread")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm into dish" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
  });

  it("navigates to the Menu Management create form with the expected state on Confirm", async () => {
    // Arrange
    stubSuggestions([suggestion()]);
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("Roasted Zucchini Flatbread");
    await user.click(screen.getByRole("button", { name: "Confirm into dish" }));

    // Assert
    expect(navigateMock).toHaveBeenCalledWith("/admin/menu", {
      state: {
        prefillName: "Roasted Zucchini Flatbread",
        prefillDescription: "Sliced thin, served on a wooden board.",
        sourceSuggestionId: 1,
      },
    });
  });

  it("calls the dismiss endpoint directly on Dismiss, with no confirm step", async () => {
    // Arrange
    let dismissCalled = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/dismiss")) {
          dismissCalled = true;
          expect(init.method).toBe("POST");
          return Promise.resolve(jsonResponse(200, suggestion({ dismissed: true })));
        }
        return Promise.resolve(jsonResponse(200, [suggestion()]));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("Roasted Zucchini Flatbread");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    // Assert
    await vi.waitFor(() => expect(dismissCalled).toBe(true));
  });
});
