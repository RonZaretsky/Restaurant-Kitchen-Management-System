import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import * as authService from "../../services/authService";
import { LoginPage } from "./LoginPage";

vi.mock("../../services/authService", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/authService")>();
  return { ...actual, useCurrentUser: vi.fn(), useLogin: vi.fn() };
});

function renderLoginPage() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    // Arrange: not authenticated, so the Navigate-away branch never fires.
    vi.mocked(authService.useCurrentUser).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      isSuccess: false,
      error: new Error("Not authenticated"),
    } as unknown as ReturnType<typeof authService.useCurrentUser>);
  });

  it("shows the generic invalid-credentials message inline on failure and stays on the form", async () => {
    // Arrange
    vi.mocked(authService.useLogin).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: true,
      error: new Error("Invalid username or password"),
    } as unknown as ReturnType<typeof authService.useLogin>);
    const user = userEvent.setup();

    // Act
    renderLoginPage();
    await user.type(screen.getByLabelText("Username"), "dcohen");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // Assert
    expect(screen.getByText("Invalid username or password")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("calls the login mutation with the submitted credentials", async () => {
    // Arrange
    const mutate = vi.fn();
    vi.mocked(authService.useLogin).mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof authService.useLogin>);
    const user = userEvent.setup();

    // Act
    renderLoginPage();
    await user.type(screen.getByLabelText("Username"), "dcohen");
    await user.type(screen.getByLabelText("Password"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // Assert
    expect(mutate).toHaveBeenCalledWith(
      { username: "dcohen", password: "correct-password" },
      expect.anything(),
    );
  });
});
