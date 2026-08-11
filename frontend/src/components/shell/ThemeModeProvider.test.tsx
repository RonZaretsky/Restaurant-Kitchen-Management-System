import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as authService from "../../services/authService";
import type { CurrentUser } from "../../types/user";
import { ThemeModeProvider, useThemeMode } from "./ThemeModeProvider";

vi.mock("../../services/authService", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/authService")>();
  return { ...actual, useCurrentUser: vi.fn() };
});

function Probe() {
  const { mode, toggleMode } = useThemeMode();
  return <button onClick={toggleMode}>mode: {mode}</button>;
}

function mockCurrentUser(role: CurrentUser["role"] | undefined) {
  vi.mocked(authService.useCurrentUser).mockReturnValue({
    data: role
      ? {
          id: 1,
          username: "test_user",
          full_name: "Test User",
          role,
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
        }
      : undefined,
    isLoading: false,
    isError: !role,
    isSuccess: Boolean(role),
    error: role ? null : new Error("Not authenticated"),
  } as unknown as ReturnType<typeof authService.useCurrentUser>);
}

function renderProbe() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeModeProvider>
        <Probe />
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("ThemeModeProvider", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("defaults to dark for a Cook with no stored preference", () => {
    // Arrange
    mockCurrentUser("cook");

    // Act
    renderProbe();

    // Assert
    expect(screen.getByRole("button")).toHaveTextContent("mode: dark");
  });

  it("defaults to light for every other role with no stored preference", () => {
    // Arrange
    mockCurrentUser("admin");

    // Act
    renderProbe();

    // Assert
    expect(screen.getByRole("button")).toHaveTextContent("mode: light");
  });

  it("toggling flips the mode and persists it to localStorage", async () => {
    // Arrange
    mockCurrentUser("admin");
    const user = userEvent.setup();
    renderProbe();

    // Act
    await user.click(screen.getByRole("button"));

    // Assert
    expect(screen.getByRole("button")).toHaveTextContent("mode: dark");
    expect(localStorage.getItem("rkms-theme-mode")).toBe("dark");
  });
});
