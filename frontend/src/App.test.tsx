import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders the application title", () => {
    // Arrange
    render(<App />);

    // Act
    const heading = screen.getByRole("heading", {
      name: /restaurant kitchen management system/i,
    });

    // Assert
    expect(heading).toBeInTheDocument();
  });
});
