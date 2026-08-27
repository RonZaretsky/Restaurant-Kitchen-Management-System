import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ROLE_NAV_ITEMS } from "./components/shell/navigationConfig";
import { ThemeModeProvider } from "./components/shell/ThemeModeProvider";
import { routes } from "./router";
import * as authService from "./services/authService";
import { ApiError } from "./services/httpClient";
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
  // A real ApiError with status 401, because the guard now distinguishes a
  // rejected session from a transport failure and only the former signs out.
  vi.mocked(authService.useCurrentUser).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: true,
    isSuccess: false,
    error: new ApiError(401, "Not authenticated"),
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
    reset: vi.fn(),
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

  it("lets an Admin reach the Ingredients surface, which lives outside the /admin prefix (Story 2.6 AC4)", async () => {
    // Arrange: POST /api/inventory/ingredients permits admin and
    // warehouse_manager alike, so gating the screen on the /admin prefix alone
    // made the backend's grant unreachable for one of the two Roles it names.
    mockAuthenticated("admin");

    // Act
    renderAt("/warehouse/ingredients");

    // Assert: the Ingredients screen itself, not a bounce to /admin/menu.
    expect(await screen.findByRole("heading", { name: "Ingredients" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Menu Management" })).not.toBeInTheDocument();
  });

  it("still bounces a Role with no Ingredients nav entry away from that surface", async () => {
    // Arrange: the cross-prefix grant is per-Role and derived from the nav
    // config, not a blanket removal of the guard.
    mockAuthenticated("waiter");

    // Act
    renderAt("/warehouse/ingredients");

    // Assert
    expect(await screen.findByRole("heading", { name: "Tables" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Ingredients" })).not.toBeInTheDocument();
  });

  it("bounces an Admin from a warehouse surface their nav does NOT list", async () => {
    // Arrange: the negative case of the cross-prefix clause, for the only Role
    // that has one. Without this, `canRoleVisit` could be rewritten as a
    // hardcoded `role === "admin"` exception and every other test still passes,
    // which is exactly the anti-pattern deriving from ROLE_NAV_ITEMS prevents.
    mockAuthenticated("admin");

    // Act
    renderAt("/warehouse/alerts");

    // Assert
    expect(await screen.findByRole("heading", { name: "Menu Management" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Alerts" })).not.toBeInTheDocument();
  });

  it("lets an Admin reach an Ingredient's detail page via includeSubroutes (this batch's #2)", async () => {
    // Arrange: /warehouse/ingredients/:ingredientId is Story 4.1's surface. FR-16 gives Admin the
    // same ingredient-management rights as Warehouse Manager, so withholding just the detail page
    // was the gap; Admin's Ingredients nav entry now opts into includeSubroutes to close it.
    mockAuthenticated("admin");

    // Act
    renderAt("/warehouse/ingredients/1");

    // Assert: reached the Ingredient detail surface, not bounced to Menu Management. This route
    // does not stub fetch, so the page's data never resolves and its heading stays on its bare
    // "Ingredient" fallback (rendered unconditionally, ahead of the loading/error/data states),
    // which is enough to prove the route itself was reached.
    expect(await screen.findByRole("heading", { name: "Ingredient" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Menu Management" })).not.toBeInTheDocument();
  });

  it("keeps a Role's own prefix granting its detail routes", async () => {
    // Arrange: the prefix clause must stay a subtree grant even though the nav
    // clause is exact, or every detail route would need its own nav entry.
    // Story 4.1 replaced IngredientDetailPage's static "Ingredient detail"
    // placeholder with real content; this test does not stub fetch, so the
    // page's data never resolves and its heading stays on its "Ingredient"
    // fallback (rendered unconditionally, ahead of the loading/error/data
    // states), which is enough to prove the route itself was reached rather
    // than the visitor being bounced elsewhere.
    mockAuthenticated("warehouse_manager");

    // Act
    renderAt("/warehouse/ingredients/1");

    // Assert: reached the surface rather than being bounced home.
    expect(await screen.findByRole("heading", { name: "Ingredient" })).toBeInTheDocument();
  });

  it("keeps tab order aligned with the app bar's left-to-right visual order (AC8)", async () => {
    // Arrange
    mockAuthenticated("admin");
    const user = userEvent.setup();

    // Act
    // The expected order comes from the nav config, not from the rendered DOM.
    // Deriving it from the DOM made this assertion tautological: plain anchors
    // with no tabindex are always tabbed in DOM order, so it could not fail.
    const expectedLabels = ROLE_NAV_ITEMS.admin.map((item) => item.label);
    renderAt("/");
    await screen.findByRole("navigation");

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
    // Arrange: LoginPage renders its form first (current-user query still
    // unauthenticated), then the session is already refreshed by the time the
    // mutation reports success.
    //
    // The ordering is supplied by this mock, it is NOT evidence that the real
    // code produces it. The real handover, where useLogin must await its own
    // cache invalidation before the caller navigates, is covered end to end in
    // appIntegration.test.tsx against the real service. What this test pins is
    // narrower: that LoginPage routes to the Role home named by the mutation
    // result rather than to a fixed path.
    mockUnauthenticated();
    vi.mocked(authService.useLogin).mockReturnValue({
      mutate: (
        _payload: { username: string; password: string },
        options?: { onSuccess?: (data: { role: UserRole }) => void },
      ) => {
        mockAuthenticated("cook");
        options?.onSuccess?.({ role: "cook" });
      },
      reset: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof authService.useLogin>);
    const user = userEvent.setup();

    // Act
    renderAt("/login");
    await user.type(screen.getByLabelText(/Username/), "acohen");
    await user.type(screen.getByLabelText(/Password/), "correct-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // Assert
    expect(await screen.findByRole("heading", { name: "Kitchen Display" })).toBeInTheDocument();
  });
});
