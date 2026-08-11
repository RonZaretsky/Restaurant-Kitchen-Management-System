import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import * as authService from "../../services/authService";
import { ApiError } from "../../services/httpClient";
import { LoginPage } from "./LoginPage";

vi.mock("../../services/authService", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/authService")>();
  return { ...actual, useCurrentUser: vi.fn(), useLogin: vi.fn() };
});

function mockLoginFailure(error: Error) {
  vi.mocked(authService.useLogin).mockReturnValue({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isError: true,
    error,
  } as unknown as ReturnType<typeof authService.useLogin>);
}

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
      error: new ApiError(401, "Not authenticated"),
    } as unknown as ReturnType<typeof authService.useCurrentUser>);
  });

  it("shows the generic invalid-credentials message inline on failure and stays on the form", async () => {
    // Arrange
    mockLoginFailure(new ApiError(401, "Invalid username or password"));
    const user = userEvent.setup();

    // Act
    renderLoginPage();
    await user.type(screen.getByLabelText(/Username/), "dcohen");
    await user.type(screen.getByLabelText(/Password/), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // Assert
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid username or password");
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("never leaks a backend validation message into the error line (AC3)", async () => {
    // Arrange
    // A 422 carries Pydantic's own wording, which must not reach the User.
    mockLoginFailure(new ApiError(422, "String should have at least 1 character"));

    // Act
    renderLoginPage();

    // Assert
    const alert = screen.getByRole("alert");
    expect(alert).not.toHaveTextContent("String should have at least 1 character");
    expect(alert).toHaveTextContent("Something went wrong. Try again.");
  });

  it("says the server is unreachable rather than blaming the credentials", async () => {
    // Arrange
    mockLoginFailure(new ApiError(0, "Cannot reach the server. Check your connection and try again."));

    // Act
    renderLoginPage();

    // Assert
    expect(screen.getByRole("alert")).toHaveTextContent("Cannot reach the server");
  });

  it("links the error line to both fields so it is announced with them", async () => {
    // Arrange
    mockLoginFailure(new ApiError(401, "Invalid username or password"));

    // Act
    renderLoginPage();

    // Assert
    const errorId = screen.getByRole("alert").id;
    expect(screen.getByLabelText(/Username/)).toHaveAttribute("aria-describedby", errorId);
    expect(screen.getByLabelText(/Password/)).toHaveAttribute("aria-describedby", errorId);
  });

  it("calls the login mutation with the submitted credentials", async () => {
    // Arrange
    const mutate = vi.fn();
    vi.mocked(authService.useLogin).mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof authService.useLogin>);
    const user = userEvent.setup();

    // Act
    renderLoginPage();
    await user.type(screen.getByLabelText(/Username/), "dcohen");
    await user.type(screen.getByLabelText(/Password/), "correct-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // Assert
    expect(mutate).toHaveBeenCalledWith(
      { username: "dcohen", password: "correct-password" },
      expect.anything(),
    );
  });
});
