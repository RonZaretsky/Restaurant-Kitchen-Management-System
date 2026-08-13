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
  return render(
    <QueryClientProvider client={queryClient}>
      <UsersPage />
    </QueryClientProvider>,
  );
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

  it("creates a user and clears the form once the mutation resolves", async () => {
    // Arrange
    let users: Array<typeof CURRENT_ADMIN> = [CURRENT_ADMIN];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.includes("/api/admin/users") && init.method === "POST") {
          const body = JSON.parse(String(init.body));
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
    await user.type(screen.getByLabelText("Initial password"), "s3cret-pass");
    await user.click(screen.getByRole("button", { name: "+ New user" }));

    // Assert
    expect(await screen.findByText("new.cook")).toBeInTheDocument();
    expect(screen.getByLabelText("Username")).toHaveValue("");
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
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        const known = handleCurrentUser(path);
        if (known) return known;
        if (path.endsWith(`/api/admin/users/${waiter.id}`) && init.method === "PATCH") {
          Object.assign(waiter, JSON.parse(String(init.body)));
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
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument());
    expect(screen.getByText("Maya Cohen")).toBeInTheDocument();
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
    await user.click(screen.getAllByRole("button", { name: "Deactivate" })[0]);

    // Assert
    await waitFor(() => expect(screen.getAllByText("Inactive").length).toBeGreaterThan(0));
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

    // Assert
    expect(await screen.findByText("Rejected, at least one admin must stay active")).toBeInTheDocument();
    expect(screen.getAllByText("Active").length).toBe(2);
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
    expect(screen.queryByDisplayValue("brand-new-pass")).not.toBeInTheDocument();
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
