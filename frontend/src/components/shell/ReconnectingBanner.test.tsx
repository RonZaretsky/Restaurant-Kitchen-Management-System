import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConnectionStatusProvider } from "./ConnectionStatusContext";
import { ReconnectingBanner } from "./ReconnectingBanner";

describe("ReconnectingBanner", () => {
  it("renders nothing under the default connected status", () => {
    // Arrange / Act
    render(
      <ConnectionStatusProvider>
        <ReconnectingBanner />
      </ConnectionStatusProvider>,
    );

    // Assert
    expect(screen.queryByText("Reconnecting...")).not.toBeInTheDocument();
  });

  it("renders the Reconnecting message when the status is reconnecting", () => {
    // Arrange / Act
    render(
      <ConnectionStatusProvider status="reconnecting">
        <ReconnectingBanner />
      </ConnectionStatusProvider>,
    );

    // Assert
    expect(screen.getByText("Reconnecting...")).toBeInTheDocument();
  });

  it("renders the replaced-by-another-tab message when the status is replaced", () => {
    // Arrange / Act
    render(
      <ConnectionStatusProvider status="replaced">
        <ReconnectingBanner />
      </ConnectionStatusProvider>,
    );

    // Assert
    expect(
      screen.getByText("This account is connected in another tab. Reload this tab to make it live again."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Reconnecting...")).not.toBeInTheDocument();
  });
});
