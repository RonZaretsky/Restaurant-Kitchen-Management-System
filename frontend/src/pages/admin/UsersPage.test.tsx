import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UsersPage } from "./UsersPage";

// Mocks only fetch, driving the real userService/authService hooks, matching
// TablesSetupPage.test.tsx's pattern: mocking the service itself would hide
// the invalidate-and-refetch wiring between a mutation and the list.

const CURRENT_ADMIN = {
  id: 1,
  username: "david.admin",
  full_name: "David Cohen",
  role: "admin",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const OTHER_ADMIN = {
  id: 2,
  username: "ron.admin",
  full_name: "Ron Azoulay",
  role: "admin",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const WAITER = {
  id: 3,
  username: "maya.w",
  full_name: "Maya Levi",
  role: "waiter",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const INACTIVE_WAITER = {
  id: 4,
  username: "yossi.w",
  full_name: "Yossi Har-Even",
  role: "waiter",
  is_active: false,
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

/** Every test needs /api/auth/me for AC6's "This is you" check to resolve. */
function handleCurrentUser(path: string): Promise<Response> | undefined {
  if (path.includes("/api/auth/me")) {
    return Promise.resolve(jsonResponse(200, CURRENT_ADMIN));
  }
  return undefined;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <UsersPage />
      </QueryClientProvider>,
    ),
    queryClient,
  };
}

describe("UsersPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the user list with the header counts", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        return (
          handleCurrentUser(path) ??
          (path.includes("/api/admin/users")
            ? Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, WAITER, INACTIVE_WAITER]))
            : Promise.reject(new Error(`unexpected request: ${path}`)))
        );
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("maya.w")).toBeInTheDocument();
    expect(screen.getByText("3 staff accounts · 2 active")).toBeInTheDocument();
  });

  it("creates a user with the selected role and clears every field on success", async () => {
    // Arrange
    let users: Array<typeof CURRENT_ADMIN> = [CURRENT_ADMIN];
    let postedBody: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.includes("/api/admin/users") && init.method === "POST") {
          const body = JSON.parse(String(init.body));
          postedBody = body;
          const created = {
            id: 9,
            username: body.username,
            full_name: body.full_name,
            role: body.role,
            is_active: true,
            created_at: "2026-01-01T00:00:00Z",
          };
          users = [...users, created];
          return Promise.resolve(jsonResponse(201, created));
        }
        if (path.includes("/api/admin/users")) return Promise.resolve(jsonResponse(200, users));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("david.admin");
    await user.type(screen.getByLabelText("Username"), "new.cook");
    await user.type(screen.getByLabelText("Full name"), "New Cook");
    // The Role Select must be exercised, not left at its default: a create
    // that ignored the field entirely would otherwise pass unnoticed.
    await user.click(screen.getByLabelText("Role"));
    await user.click(await screen.findByRole("option", { name: "Cook" }));
    await user.type(screen.getByLabelText("Initial password"), "s3cret-pass");
    await user.click(screen.getByRole("button", { name: "+ New user" }));

    // Assert: the selected Role actually reaches the backend.
    expect(await screen.findByText("new.cook")).toBeInTheDocument();
    await waitFor(() =>
      expect(postedBody).toEqual({
        username: "new.cook",
        full_name: "New Cook",
        role: "cook",
        password: "s3cret-pass",
      }),
    );
    // Every field clears, not only the two that were originally asserted.
    expect(screen.getByLabelText("Username")).toHaveValue("");
    expect(screen.getByLabelText("Full name")).toHaveValue("");
    expect(screen.getByLabelText("Initial password")).toHaveValue("");
  });

  it("surfaces the backend's exact duplicate-username message inline and does not clear the form", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.includes("/api/admin/users") && init.method === "POST") {
          return Promise.resolve(jsonResponse(409, { detail: "That username already exists" }));
        }
        if (path.includes("/api/admin/users")) return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("david.admin");
    await user.type(screen.getByLabelText("Username"), "david.admin");
    await user.type(screen.getByLabelText("Full name"), "Someone Else");
    await user.type(screen.getByLabelText("Initial password"), "s3cret-pass");
    await user.click(screen.getByRole("button", { name: "+ New user" }));

    // Assert
    expect(await screen.findByText("That username already exists")).toBeInTheDocument();
    expect(screen.getByLabelText("Username")).toHaveValue("david.admin");
  });

  it("edits full name and role and exits edit mode on success", async () => {
    // Arrange
    const waiter = { ...WAITER };
    let patchedBody: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.endsWith(`/api/admin/users/${waiter.id}`) && init.method === "PATCH") {
          patchedBody = JSON.parse(String(init.body));
          Object.assign(waiter, patchedBody);
          return Promise.resolve(jsonResponse(200, waiter));
        }
        if (path.includes("/api/admin/users")) return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, waiter]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("maya.w");
    // Row order is [CURRENT_ADMIN, waiter], so the waiter's Edit button is the second one.
    await user.click(screen.getAllByRole("button", { name: "Edit" })[1]);
    const nameField = screen.getByLabelText(`Full name for ${waiter.username}`);
    await user.clear(nameField);
    await user.type(nameField, "Maya Cohen");
    // The Role half of this test's own title: without this the entire role
    // branch could be deleted and the suite would stay green.
    await user.click(screen.getByLabelText(`Role for ${waiter.username}`));
    await user.click(await screen.findByRole("option", { name: "Cook" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument());
    expect(screen.getByText("Maya Cohen")).toBeInTheDocument();
    expect(patchedBody).toEqual({ full_name: "Maya Cohen", role: "cook" });
  });

  it("deactivates an active user and flips the status chip", async () => {
    // Arrange
    const waiter = { ...WAITER };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.endsWith(`/api/admin/users/${waiter.id}/deactivate`) && init.method === "POST") {
          waiter.is_active = false;
          return Promise.resolve(jsonResponse(200, waiter));
        }
        if (path.includes("/api/admin/users")) return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, waiter]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("maya.w");
    expect(screen.queryByText("Inactive")).not.toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Deactivate" })[0]);
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    // Assert: exactly the one row flips, and the count is pinned 0 -> 1 so a
    // component that wrongly flipped every row would fail this too.
    await waitFor(() => expect(screen.getAllByText("Inactive")).toHaveLength(1));
  });

  it("asks for confirmation before deactivating, and sends nothing if cancelled", async () => {
    // Arrange
    const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
      void init;
      const path = String(url);
      const known = handleCurrentUser(path);
      if (known) return known;
      if (path.includes("/api/admin/users")) return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, WAITER]));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("maya.w");
    await user.click(screen.getByRole("button", { name: "Deactivate" }));

    // Assert: the confirm names the user, and nothing is sent until confirmed.
    expect(screen.getByText("Deactivate Maya Levi?")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/deactivate")),
    ).toBe(false);

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Deactivate Maya Levi?")).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/deactivate")),
    ).toBe(false);
  });

  it("surfaces the exact last-admin-lockout message and the chip stays Active", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.endsWith(`/api/admin/users/${OTHER_ADMIN.id}/deactivate`) && init.method === "POST") {
          return Promise.resolve(
            jsonResponse(409, { detail: "Rejected, at least one admin must stay active" }),
          );
        }
        if (path.includes("/api/admin/users"))
          return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, OTHER_ADMIN]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("ron.admin");
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    // Assert: the exact backend string, and no row silently flipped. (The
    // chip count alone cannot fail here — the mock always returns both users
    // active — so the real assertion is that "Inactive" never appears.)
    expect(await screen.findByText("Rejected, at least one admin must stay active")).toBeInTheDocument();
    expect(screen.queryByText("Inactive")).not.toBeInTheDocument();
  });

  it("reactivates a deactivated user", async () => {
    // Arrange
    const waiter = { ...INACTIVE_WAITER };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.endsWith(`/api/admin/users/${waiter.id}/reactivate`) && init.method === "POST") {
          waiter.is_active = true;
          return Promise.resolve(jsonResponse(200, waiter));
        }
        if (path.includes("/api/admin/users")) return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, waiter]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("yossi.w");
    await user.click(screen.getByRole("button", { name: "Reactivate" }));

    // Assert
    await waitFor(() => expect(screen.getAllByText("Active").length).toBe(2));
  });

  it("resets a user's password and clears the field without ever re-displaying the value", async () => {
    // Arrange
    const waiter = { ...WAITER };
    let receivedPassword: string | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.endsWith(`/api/admin/users/${waiter.id}/reset-password`) && init.method === "POST") {
          receivedPassword = JSON.parse(String(init.body)).new_password;
          return Promise.resolve(jsonResponse(200, waiter));
        }
        if (path.includes("/api/admin/users")) return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, waiter]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("maya.w");
    await user.click(screen.getAllByRole("button", { name: "Reset password" })[1]);
    const passwordField = screen.getByLabelText(`New password for ${waiter.username}`);
    await user.type(passwordField, "brand-new-pass");
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    await waitFor(() => expect(receivedPassword).toBe("brand-new-pass"));
    // The panel closes on success, so asserting the value is gone from the DOM
    // proves nothing on its own. Re-open the panel and assert the field is
    // genuinely empty, which is what actually pins the state being cleared.
    await waitFor(() =>
      expect(
        screen.queryByLabelText(`New password for ${waiter.username}`),
      ).not.toBeInTheDocument(),
    );
    await user.click(screen.getAllByRole("button", { name: "Reset password" })[1]);
    expect(screen.getByLabelText(`New password for ${waiter.username}`)).toHaveValue("");
  });

});
