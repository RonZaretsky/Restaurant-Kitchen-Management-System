import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeModeProvider } from "./components/shell/ThemeModeProvider";
import { routes } from "./router";
import * as authService from "./services/authService";
import type { CurrentUser, UserRole } from "./types/user";

vi.mock("./services/authService", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./services/authService")>();
  return { ...actual, useCurrentUser: vi.fn(), useLogin: vi.fn() };
});

function mockUser(role: UserRole): CurrentUser {
  return {
    id: 1,
    username: "test_user",
    full_name: "Test User",
    role,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function mockAuthenticated(role: UserRole) {
  vi.mocked(authService.useCurrentUser).mockReturnValue({
    data: mockUser(role),
    isLoading: false,
    isError: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof authService.useCurrentUser>);
}

function mockUnauthenticated() {
  vi.mocked(authService.useCurrentUser).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: true,
    isSuccess: false,
    error: new Error("Not authenticated"),
  } as unknown as ReturnType<typeof authService.useCurrentUser>);
}

function mockLoading() {
  vi.mocked(authService.useCurrentUser).mockReturnValue({
    data: undefined,
    isLoading: true,
    isError: false,
    isSuccess: false,
    error: null,
  } as unknown as ReturnType<typeof authService.useCurrentUser>);
}

function mockNoOpLogin() {
  vi.mocked(authService.useLogin).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof authService.useLogin>);
}

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const memoryRouter = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeModeProvider>
        <RouterProvider router={memoryRouter} />
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("route guard and per-role navigation", () => {
  beforeEach(() => {
    // Arrange: every test gets a harmless default login mutation; tests that
    // exercise the login flow itself override this before calling renderAt.
    mockNoOpLogin();
  });

  it("redirects an unauthenticated visit to any protected surface to Login (AC1)", async () => {
    // Arrange
    mockUnauthenticated();

    // Act
    renderAt("/waiter/tables");

    // Assert
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("redirects an already-authenticated visit to Login to the caller's role home (AC2)", async () => {
    // Arrange
    mockAuthenticated("waiter");

    // Act
    renderAt("/login");

    // Assert
    expect(await screen.findByRole("heading", { name: "Tables" })).toBeInTheDocument();
  });

  it("renders a loading skeleton while the session is still resolving (AC6)", () => {
    // Arrange
    mockLoading();

    // Act
    renderAt("/waiter/tables");

    // Assert
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });

  it.each([
    ["admin", "Menu Management"],
    ["waiter", "Tables"],
    ["cook", "Kitchen Display"],
    ["warehouse_manager", "Ingredients"],
  ] as const)("logs in a %s onto their own role's home surface", async (role, expectedHeading) => {
    // Arrange
    mockAuthenticated(role);

    // Act
    renderAt("/");

    // Assert
    expect(await screen.findByRole("heading", { name: expectedHeading })).toBeInTheDocument();
  });

  it("shows a Cook only their own nav entries, never another role's surfaces", async () => {
    // Arrange
    mockAuthenticated("cook");

    // Act
    renderAt("/");
    const nav = await screen.findByRole("navigation");

    // Assert
    expect(within(nav).getByText("Kitchen Display")).toBeInTheDocument();
    expect(within(nav).getByText("Dishes")).toBeInTheDocument();
    expect(within(nav).getByText("Smart Chef")).toBeInTheDocument();
    expect(within(nav).queryByText("Tables")).not.toBeInTheDocument();
    expect(within(nav).queryByText("Users")).not.toBeInTheDocument();
    expect(within(nav).queryByText("Ingredients")).not.toBeInTheDocument();
  });

  it("redirects a direct cross-role URL visit to the caller's own home surface, not the other role's page", async () => {
    // Arrange
    mockAuthenticated("waiter");

    // Act
    renderAt("/admin/users");

    // Assert
    expect(await screen.findByRole("heading", { name: "Tables" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Users" })).not.toBeInTheDocument();
  });

  it("keeps tab order aligned with the app bar's left-to-right visual order (AC8)", async () => {
    // Arrange
    mockAuthenticated("admin");
    const user = userEvent.setup();

    // Act
    renderAt("/");
    const nav = await screen.findByRole("navigation");
    const expectedLabels = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent);

    document.body.focus();
    const focusedLabels: (string | null)[] = [];
    for (let i = 0; i < expectedLabels.length; i += 1) {
      await user.tab();
      focusedLabels.push(document.activeElement?.textContent ?? null);
    }

    // Assert
    expect(focusedLabels).toEqual(expectedLabels);
  });

  it("navigates to the role's home surface immediately after a successful login (AC2, AC3)", async () => {
    // Arrange: LoginPage must render its form first (current-user query still
    // unauthenticated), then flip to authenticated the moment the mutation
    // "succeeds", mirroring the real invalidateQueries()-triggered refetch
    // landing before the destination route's own guard re-evaluates.
    mockUnauthenticated();
    vi.mocked(authService.useLogin).mockReturnValue({
      mutate: (
        _payload: { username: string; password: string },
        options?: { onSuccess?: (data: { role: UserRole }) => void },
      ) => {
        mockAuthenticated("cook");
        options?.onSuccess?.({ role: "cook" });
      },
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof authService.useLogin>);
    const user = userEvent.setup();

    // Act
    renderAt("/login");
    await user.type(screen.getByLabelText("Username"), "acohen");
    await user.type(screen.getByLabelText("Password"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // Assert
    expect(await screen.findByRole("heading", { name: "Kitchen Display" })).toBeInTheDocument();
  });
});
