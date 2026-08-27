import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SmartChefPage } from "./SmartChefPage";

// Mocks only fetch, driving the real smartChefService/authService hooks, matching
// TablesPage.test.tsx/KitchenDisplayPage.test.tsx's established pattern.

const CURRENT_USER = {
  id: 3,
  username: "amir",
  full_name: "Amir",
  role: "cook",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const OTHER_USER_ID = 99;

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

const OTHER_SUGGESTION = {
  ...SUGGESTION,
  id: 2,
  requested_by: OTHER_USER_ID,
  generated_recipe: { ...SUGGESTION.generated_recipe, name: "Other Cook's Suggestion" },
};

const SESSION = {
  id: 42,
  user_id: 3,
  dish_id: null,
  suggestion_id: 1,
  title: "Chat about Roasted Zucchini Flatbread",
  created_at: "2026-01-02T09:00:00Z",
};

const OTHER_SESSION = {
  id: 43,
  user_id: OTHER_USER_ID,
  dish_id: null,
  suggestion_id: 2,
  title: "Chat about Other Cook's Suggestion",
  created_at: "2026-01-02T10:00:00Z",
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

/**
 * Routes every GET this page's queries can issue (suggestions, chat sessions, the current user,
 * and one session's messages) by URL, matching `KitchenDisplayPage.test.tsx`'s own
 * multi-query `stubReads` precedent. `onPost` lets a test intercept a POST (creating a session,
 * sending a message) before falling through to the default 404 rejection.
 */
function mockFetch(options: {
  suggestions?: unknown[];
  sessions?: unknown[];
  currentUser?: unknown;
  messagesBySession?: Record<number, unknown[]>;
  onPost?: (path: string, body: Record<string, unknown>) => Response | undefined;
}) {
  const suggestions = options.suggestions ?? [];
  const sessions = options.sessions ?? [];
  const currentUser = options.currentUser ?? CURRENT_USER;
  const messagesBySession = options.messagesBySession ?? {};

  return vi.fn((url: string, init: RequestInit = {}) => {
    const path = String(url);
    const method = init.method ?? "GET";

    if (method === "POST" && options.onPost) {
      const body = init.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
      const response = options.onPost(path, body);
      if (response) return Promise.resolve(response);
    }

    if (path.endsWith("/api/auth/me")) return Promise.resolve(jsonResponse(200, currentUser));

    const messagesMatch = path.match(/\/chat-sessions\/(\d+)\/messages$/);
    if (messagesMatch) {
      const sessionId = Number(messagesMatch[1]);
      return Promise.resolve(jsonResponse(200, messagesBySession[sessionId] ?? []));
    }

    if (path.endsWith("/api/smart-chef/chat-sessions")) return Promise.resolve(jsonResponse(200, sessions));
    if (path.endsWith("/api/smart-chef/suggestions")) return Promise.resolve(jsonResponse(200, suggestions));

    return Promise.reject(new Error(`unexpected request: ${method} ${url}`));
  });
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
    vi.stubGlobal("fetch", mockFetch({}));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No recipe suggestions yet.")).toBeInTheDocument();
  });

  it("renders a suggestion card with a Discuss via chat action and no open chat panel", async () => {
    // Arrange
    vi.stubGlobal("fetch", mockFetch({ suggestions: [SUGGESTION] }));

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
    expect(screen.getByRole("button", { name: "Discuss via chat" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /ask a follow-up/i })).not.toBeInTheDocument();
  });

  it("shows a generating indicator and disables the button while the mutation is pending", async () => {
    // Arrange: the POST never resolves during this test, keeping the mutation pending.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        if (init.method === "POST" && String(url).endsWith("/api/smart-chef/suggestions")) {
          return new Promise(() => {});
        }
        return mockFetch({})(url, init);
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
      vi.fn((url: string, init: RequestInit = {}) => {
        if (init.method === "POST" && String(url).endsWith("/api/smart-chef/suggestions")) {
          return Promise.resolve(jsonResponse(502, { detail: "Couldn't generate a suggestion right now" }));
        }
        return mockFetch({})(url, init);
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
      vi.fn((url: string, init: RequestInit = {}) => {
        if (init.method === "POST" && String(url).endsWith("/api/smart-chef/suggestions")) {
          submitted = JSON.parse(String(init.body));
          return Promise.resolve(jsonResponse(201, SUGGESTION));
        }
        return mockFetch({})(url, init);
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

  it('shows "No chat sessions yet." when there are no chat sessions (AC6)', async () => {
    // Arrange
    vi.stubGlobal("fetch", mockFetch({}));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No chat sessions yet.")).toBeInTheDocument();
  });

  it("a chat session created by a different Cook still appears in the Sessions list (AC3)", async () => {
    // Arrange: no special grant needed to see another Cook's session.
    vi.stubGlobal("fetch", mockFetch({ sessions: [OTHER_SESSION] }));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Chat about Other Cook's Suggestion")).toBeInTheDocument();
  });

  it("sorts the current Cook's own items first in both the Suggestions and Sessions lists (AC3)", async () => {
    // Arrange: the server returns the other Cook's items first in both lists; the page must
    // still render the current Cook's own item first in each.
    vi.stubGlobal(
      "fetch",
      mockFetch({
        suggestions: [OTHER_SUGGESTION, SUGGESTION],
        sessions: [OTHER_SESSION, SESSION],
      }),
    );

    // Act
    const { container } = renderPage();
    await screen.findByText("Roasted Zucchini Flatbread");
    await screen.findByText("Chat about Other Cook's Suggestion");

    // Assert
    const text = container.textContent ?? "";
    expect(text.indexOf("Roasted Zucchini Flatbread")).toBeLessThan(text.indexOf("Other Cook's Suggestion"));
    expect(text.indexOf("Chat about Roasted Zucchini Flatbread")).toBeLessThan(
      text.indexOf("Chat about Other Cook's Suggestion"),
    );
  });

  it("clicking Discuss via chat creates a session and renders its chat panel", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      mockFetch({
        suggestions: [SUGGESTION],
        onPost: (path, body) => {
          if (path.endsWith("/api/smart-chef/chat-sessions")) {
            expect(body).toEqual({ suggestion_id: SUGGESTION.id });
            return jsonResponse(201, SESSION);
          }
          return undefined;
        },
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Discuss via chat" }));

    // Assert
    expect(await screen.findByLabelText("Ask a follow-up")).toBeInTheDocument();
  });

  it("clicking a Chat Session row opens its history and lets a Cook continue it", async () => {
    // Arrange
    const messagesBySession = {
      [SESSION.id]: [
        { id: 1, session_id: SESSION.id, role: "user", content: "How do I improve this?", created_at: "2026-01-02T09:01:00Z" },
        { id: 2, session_id: SESSION.id, role: "assistant", content: "Try adding basil.", created_at: "2026-01-02T09:01:05Z" },
      ],
    };
    vi.stubGlobal("fetch", mockFetch({ sessions: [SESSION], messagesBySession }));
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByText(SESSION.title));

    // Assert
    expect(await screen.findByText("How do I improve this?")).toBeInTheDocument();
    expect(screen.getByText("Try adding basil.")).toBeInTheDocument();
  });

  it("sending a message in the panel shows both the new user and assistant messages after success", async () => {
    // Arrange
    const messagesStore: Record<number, unknown[]> = { [SESSION.id]: [] };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        sessions: [SESSION],
        messagesBySession: messagesStore,
        onPost: (path, body) => {
          if (path.endsWith(`/chat-sessions/${SESSION.id}/messages`)) {
            const userMessage = {
              id: 101,
              session_id: SESSION.id,
              role: "user",
              content: body.content,
              created_at: "2026-01-02T09:05:00Z",
            };
            const assistantMessage = {
              id: 102,
              session_id: SESSION.id,
              role: "assistant",
              content: "Great idea, try that.",
              created_at: "2026-01-02T09:05:05Z",
            };
            messagesStore[SESSION.id] = [...(messagesStore[SESSION.id] ?? []), userMessage, assistantMessage];
            return jsonResponse(201, [userMessage, assistantMessage]);
          }
          return undefined;
        },
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByText(SESSION.title));
    await user.type(await screen.findByLabelText("Ask a follow-up"), "What herbs work well?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    // Assert
    expect(await screen.findByText("What herbs work well?")).toBeInTheDocument();
    expect(await screen.findByText("Great idea, try that.")).toBeInTheDocument();
  });

  it("a failed send shows an inline error, not a stuck sending state (AC4)", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      mockFetch({
        sessions: [SESSION],
        onPost: (path) => {
          if (path.endsWith(`/chat-sessions/${SESSION.id}/messages`)) {
            return jsonResponse(502, { detail: "Couldn't get a response right now" });
          }
          return undefined;
        },
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByText(SESSION.title));
    await user.type(await screen.findByLabelText("Ask a follow-up"), "What herbs work well?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    // Assert
    expect(await screen.findByText("Couldn't get a response right now")).toBeInTheDocument();
    expect(screen.queryByText("Generating reply...")).not.toBeInTheDocument();
  });
});
