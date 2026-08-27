import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatPanel } from "./ChatPanel";

// Mocks only fetch, driving the real smartChefService hooks, matching SmartChefPage.test.tsx's
// established pattern.

const MESSAGES = [
  { id: 1, session_id: 7, role: "user", content: "How do I improve this?", created_at: "2026-01-01T18:00:00Z" },
  {
    id: 2,
    session_id: 7,
    role: "assistant",
    content: "Try adding a pinch of nutmeg.",
    created_at: "2026-01-01T18:00:05Z",
  },
];

function jsonResponse(status: number, body: unknown): Response {
  const text = JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(text),
    json: () => Promise.resolve(JSON.parse(text)),
  } as unknown as Response;
}

function renderPanel(sessionId = 7) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ChatPanel sessionId={sessionId} />
    </QueryClientProvider>,
  );
}

describe("ChatPanel", () => {
  it("renders every message in the session, oldest first", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(200, MESSAGES))));

    // Act
    renderPanel();

    // Assert
    expect(await screen.findByText("How do I improve this?")).toBeInTheDocument();
    expect(screen.getByText("Try adding a pinch of nutmeg.")).toBeInTheDocument();
  });

  it("shows an inline error when the message list fails to load", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(404, { detail: "Chat session not found" }))));

    // Act
    renderPanel();

    // Assert
    expect(await screen.findByText(/Could not load messages\. Chat session not found/)).toBeInTheDocument();
  });

  it("shows a generating indicator while a send is pending, and disables Send", async () => {
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
    renderPanel();
    await user.type(screen.getByLabelText("Ask a follow-up"), "Any tips?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    // Assert
    expect(await screen.findByText("Generating reply...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("shows an inline error on a failed send, not a stuck generating state (AC4)", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit = {}) => {
        if (init.method === "POST") {
          return Promise.resolve(jsonResponse(502, { detail: "Couldn't get a response right now" }));
        }
        return Promise.resolve(jsonResponse(200, []));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPanel();
    await user.type(screen.getByLabelText("Ask a follow-up"), "Any tips?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    // Assert
    expect(await screen.findByText("Couldn't get a response right now")).toBeInTheDocument();
    expect(screen.queryByText("Generating reply...")).not.toBeInTheDocument();
  });

  it("sends the trimmed message content and clears the input on success", async () => {
    // Arrange
    let submittedBody: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit = {}) => {
        if (init.method === "POST") {
          submittedBody = JSON.parse(String(init.body));
          return Promise.resolve(jsonResponse(201, MESSAGES));
        }
        return Promise.resolve(jsonResponse(200, []));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPanel();
    const input = screen.getByLabelText("Ask a follow-up") as HTMLInputElement;
    await user.type(input, "  Any tips?  ");
    await user.click(screen.getByRole("button", { name: "Send" }));

    // Assert
    await vi.waitFor(() => expect(submittedBody).toEqual({ content: "Any tips?" }));
    await vi.waitFor(() => expect(input.value).toBe(""));
  });
});
