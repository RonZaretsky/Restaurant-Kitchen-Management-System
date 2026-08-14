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

  it("always sends both fields, so an edit matching a stale cached value still saves", async () => {
    // Arrange: diffing the drafts against the cached row means re-typing the
    // value the cache shows produces an empty payload, no request, and a row
    // that looks saved while the server holds something else. It also lets a
    // save silently revert a concurrent change to the field left untouched.
    const waiter = { ...WAITER };
    const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
      const path = String(url);
      const known = handleCurrentUser(path);
      if (known) return known;
      if (path.endsWith(`/api/admin/users/${waiter.id}`) && init.method === "PATCH") {
        return Promise.resolve(jsonResponse(200, waiter));
      }
      if (path.includes("/api/admin/users")) return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, waiter]));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act: save without changing anything the client can see.
    renderPage();
    await screen.findByText("maya.w");
    await user.click(screen.getAllByRole("button", { name: "Edit" })[1]);
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert: a request still goes out, carrying both fields.
    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === "PATCH");
      expect(patch).toBeDefined();
      expect(JSON.parse(String((patch![1] as RequestInit).body))).toEqual({
        full_name: "Maya Levi",
        role: "waiter",
      });
    });
  });

  it("surfaces the exact last-admin message when a demoting role change is rejected", async () => {
    // Arrange: AC5 covers a demoting PATCH as well as deactivation, and only
    // the deactivate half was previously proven.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.endsWith(`/api/admin/users/${OTHER_ADMIN.id}`) && init.method === "PATCH") {
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
    await user.click(screen.getAllByRole("button", { name: "Edit" })[1]);
    await user.click(screen.getByLabelText(`Role for ${OTHER_ADMIN.username}`));
    await user.click(await screen.findByRole("option", { name: "Waiter" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    expect(await screen.findByText("Rejected, at least one admin must stay active")).toBeInTheDocument();
  });

  it("clears a failed action's error once a different action on the same row succeeds", async () => {
    // Arrange: deactivate/reactivate were never reset(), so a 409 alert
    // outlived the action that caused it and reappeared under a later,
    // fully successful edit on the same row.
    const admin = { ...OTHER_ADMIN };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.endsWith(`/api/admin/users/${admin.id}/deactivate`) && init.method === "POST") {
          return Promise.resolve(
            jsonResponse(409, { detail: "Rejected, at least one admin must stay active" }),
          );
        }
        if (path.endsWith(`/api/admin/users/${admin.id}`) && init.method === "PATCH") {
          Object.assign(admin, JSON.parse(String(init.body)));
          return Promise.resolve(jsonResponse(200, admin));
        }
        if (path.includes("/api/admin/users")) return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, admin]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act: fail a deactivate, then succeed at an unrelated rename.
    renderPage();
    await screen.findByText("ron.admin");
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Rejected, at least one admin must stay active")).toBeInTheDocument();

    // Back out of the confirm; the error deliberately survives this, which is
    // exactly the state that used to leak into the next successful action.
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Rejected, at least one admin must stay active")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Edit" })[1]);
    const nameField = screen.getByLabelText(`Full name for ${admin.username}`);
    await user.clear(nameField);
    await user.type(nameField, "Ron Azoulay Jr");
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert: the stale failure does not survive the successful action.
    await waitFor(() => expect(screen.getByText("Ron Azoulay Jr")).toBeInTheDocument());
    expect(
      screen.queryByText("Rejected, at least one admin must stay active"),
    ).not.toBeInTheDocument();
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

  it("shows \"This is you\" with no Deactivate button on the signed-in admin's own row, while other rows have one", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        return (
          handleCurrentUser(path) ??
          (path.includes("/api/admin/users")
            ? Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, OTHER_ADMIN]))
            : Promise.reject(new Error(`unexpected request: ${path}`)))
        );
      }),
    );

    // Act
    renderPage();

    // Assert: exactly one Deactivate button (Ron's row), and "This is you" on David's.
    await screen.findByText("ron.admin");
    expect(screen.getByText("This is you")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Deactivate" })).toHaveLength(1);
  });

  it("withholds Deactivate from every row while the signed-in admin is unknown", async () => {
    // Arrange: with /api/auth/me failing, the page cannot tell which row is
    // the signed-in Admin's. Treating "unknown" as "not me" would render a
    // live Deactivate on their own row, and the backend has no self-guard.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/auth/me")) {
          return Promise.resolve(jsonResponse(401, { detail: "Not authenticated" }));
        }
        if (path.includes("/api/admin/users")) {
          return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, OTHER_ADMIN]));
        }
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    await screen.findByText("ron.admin");
    expect(screen.queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
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

  it("keeps the list and an open editor mounted when a background refetch fails", async () => {
    // Arrange: TanStack retains data when a refetch errors. Hiding the table
    // on isError therefore unmounts every open editor and any typed password
    // over a momentary blip; an alt-tab is enough to trigger it.
    let failNext = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.includes("/api/admin/users")) {
          if (failNext) return Promise.reject(new TypeError("Failed to fetch"));
          return Promise.resolve(jsonResponse(200, [CURRENT_ADMIN, WAITER]));
        }
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act: open an editor, then make the next refetch fail. Invalidating the
    // query is what a window-focus refetch or any sibling mutation does.
    const { queryClient } = renderPage();
    await screen.findByText("maya.w");
    await user.click(screen.getAllByRole("button", { name: "Edit" })[1]);
    const nameField = screen.getByLabelText(`Full name for ${WAITER.username}`);
    await user.clear(nameField);
    await user.type(nameField, "Half-typed name");
    failNext = true;
    await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });

    // Assert: the error is shown alongside the table, and the in-progress
    // edit survives rather than being destroyed.
    expect(await screen.findByText(/Could not load the users/)).toBeInTheDocument();
    expect(screen.getByLabelText(`Full name for ${WAITER.username}`)).toHaveValue("Half-typed name");
    expect(screen.getByText("maya.w")).toBeInTheDocument();
  });

  it("shows an empty state when there are no users", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        return (
          handleCurrentUser(path) ??
          (path.includes("/api/admin/users")
            ? Promise.resolve(jsonResponse(200, []))
            : Promise.reject(new Error(`unexpected request: ${path}`)))
        );
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No users yet.")).toBeInTheDocument();
  });

  it("shows an error with a retry when the user list cannot be loaded", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        return Promise.reject(new TypeError("Failed to fetch"));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText(/Could not load the users/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
