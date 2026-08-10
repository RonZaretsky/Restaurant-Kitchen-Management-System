import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import * as authService from "./services/authService";

// App.tsx became the provider composition root in Story 1.4, replacing the
// old bare-<h1> placeholder this file used to assert on. This smoke test
// covers the same ground at the new root: an unauthenticated visitor ends
// up on the Login screen, proving the full provider stack (Query, theme,
// router, route guard) wires together correctly.
vi.mock("./services/authService", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./services/authService")>();
  return { ...actual, useCurrentUser: vi.fn(), useLogin: vi.fn() };
});

describe("App", () => {
  it("sends an unauthenticated visitor to the Login screen", async () => {
    // Arrange
    vi.mocked(authService.useCurrentUser).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      isSuccess: false,
      error: new Error("Not authenticated"),
    } as unknown as ReturnType<typeof authService.useCurrentUser>);
    vi.mocked(authService.useLogin).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof authService.useLogin>);

    // Act
    render(<App />);

    // Assert
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});
