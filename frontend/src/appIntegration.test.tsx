import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeModeProvider } from "./components/shell/ThemeModeProvider";
import { routes } from "./router";

// The one test file that does NOT mock authService. Everything else stubs the
// hooks, which means the query-to-guard interaction, the retry policy, and the
// login invalidation never actually run there. This drives the real service
// over a stubbed fetch instead, which is the only level at which the
// post-login handover between the mutation and the route guard is observable.

const COOK = {
  id: 7,
  username: "acohen",
  full_name: "Avi Cohen",
  role: "cook",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
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
 * Resolves after a real timer tick rather than a microtask.
 *
 * The session refetch has to be genuinely slower than the navigation for the
 * post-login handover to be observable at all. With an instantly-resolved stub
 * the refetch lands before React re-renders, and the bounce this file exists to
 * catch cannot happen even when the bug is present.
 */
function delayed(response: Response): Promise<Response> {
  return new Promise((resolve) => setTimeout(() => resolve(response), 25));
}

describe("login through to the Role home surface, against the real auth service", () => {
  let signedIn = false;

  beforeEach(() => {
    signedIn = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/auth/login")) {
          signedIn = true;
          return Promise.resolve(jsonResponse(200, { role: "cook" }));
        }
        if (path.includes("/api/auth/me")) {
          return signedIn
            ? delayed(jsonResponse(200, COOK))
            : Promise.resolve(jsonResponse(401, { detail: "Not authenticated" }));
        }
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lands on Kitchen Display without bouncing back through Login", async () => {
    // Arrange
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const memoryRouter = createMemoryRouter(routes, { initialEntries: ["/login"] });
    const visited: string[] = [];
    memoryRouter.subscribe((state) => visited.push(state.location.pathname));
    const user = userEvent.setup();

    // Act
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeModeProvider>
          <RouterProvider router={memoryRouter} />
        </ThemeModeProvider>
      </QueryClientProvider>,
    );
    await user.type(await screen.findByLabelText(/Username/), "acohen");
    await user.type(screen.getByLabelText(/Password/), "correct-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // Assert
    expect(await screen.findByRole("heading", { name: "Kitchen Display" })).toBeInTheDocument();
    // The User reaches their home in one hop. Any regression that lets the guard
    // read a stale rejected session after a successful login shows up here as a
    // second "/login" entry before Kitchen Display.
    expect(visited).not.toContain("/login");
  });

  it("keeps the User signed in when the session check fails for a transport reason", async () => {
    // Arrange
    // A dead backend must not read as "signed out", or a blip silently ejects a
    // working session to the Login screen.
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const memoryRouter = createMemoryRouter(routes, {
      initialEntries: ["/cook/kitchen-display"],
    });

    // Act
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeModeProvider>
          <RouterProvider router={memoryRouter} />
        </ThemeModeProvider>
      </QueryClientProvider>,
    );

    // Assert
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument();
  });
});
