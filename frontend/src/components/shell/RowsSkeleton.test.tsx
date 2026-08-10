import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RowsSkeleton } from "./RowsSkeleton";

describe("RowsSkeleton", () => {
  it("renders the requested number of rows as a single loading region", () => {
    // Arrange / Act
    render(<RowsSkeleton count={4} />);

    // Assert
    const region = screen.getByRole("status", { name: "Loading" });
    expect(region.children).toHaveLength(4);
  });
});
