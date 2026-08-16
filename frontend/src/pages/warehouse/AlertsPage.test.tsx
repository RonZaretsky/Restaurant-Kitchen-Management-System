import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RealtimeProvider } from "../../components/shell/RealtimeProvider";
import { AlertsPage } from "./AlertsPage";

// Mocks only fetch, driving the real inventoryService hooks, matching
// TablesPage.test.tsx's established pattern.

const LOW_INGREDIENT = {
  id: 1,
  name: "Basil",
  unit: "kg",
  current_stock: "0.500",
  min_stock_threshold: "2.000",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const navigateMock = vi.fn();
vi.mock("react-router", async () => {
  const actual = await vi.importActual<typeof import("react-router")>("react-router");
  return { ...actual, useNavigate: () => navigateMock };
});

function jsonResponse(status: number, body: unknown): Response {
  const text = JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(text),
    json: () => Promise.resolve(JSON.parse(text)),
  } as unknown as Response;
}

/**
 * A minimal stand-in for the browser's WebSocket, copied from
 * TablesPage.test.tsx/RealtimeProvider.test.tsx (continuing the existing
 * per-test-file-copy precedent rather than extracting a shared module, per
 * deferred-work.md's own note on that call).
 */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  url: string;
  readyState = 1; // OPEN
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close(code = 1006) {
    this.readyState = 3; // CLOSED
    this.onclose?.({ code });
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RealtimeProvider>
          <AlertsPage />
        </RealtimeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AlertsPage", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    navigateMock.mockClear();
  });

  it("shows 'No active shortages' when the list is empty", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(200, []))));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No active shortages")).toBeInTheDocument();
  });

  it("renders one alert row per ingredient in shortage, in the exact copy format", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(200, [LOW_INGREDIENT]))));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Stock low: Basil (0.500kg left)")).toBeInTheDocument();
  });

  it("navigates to the ingredient's detail page when a row is clicked", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(200, [LOW_INGREDIENT]))));
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByText("Stock low: Basil (0.500kg left)"));

    // Assert
    expect(navigateMock).toHaveBeenCalledWith("/warehouse/ingredients/1");
  });

  it("shows a retry-capable error when the alerts list cannot be loaded", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));

    // Act
    renderPage();

    // Assert
    expect(
      await screen.findByText("Cannot reach the server. Check your connection and try again."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("refetches the alerts list when a live inventory.alerts_changed event arrives", async () => {
    // Arrange: starts with no shortages, then the backend reports one active
    // shortage on the second fetch, simulating another terminal's movement.
    let alerts: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(200, alerts))),
    );

    // Act
    renderPage();
    await screen.findByText("No active shortages");
    alerts = [LOW_INGREDIENT];
    const socket = FakeWebSocket.instances[0];
    expect(socket).toBeDefined();
    socket.onmessage?.({
      data: JSON.stringify({ event: "inventory.alerts_changed", payload: { ingredient_id: 1 } }),
    });

    // Assert
    expect(await screen.findByText("Stock low: Basil (0.500kg left)")).toBeInTheDocument();
  });
});
