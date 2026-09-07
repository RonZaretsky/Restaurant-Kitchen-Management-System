import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentUser } from "../../types/user";
import { AppShell } from "./AppShell";
import { RealtimeProvider } from "./RealtimeProvider";
import { ThemeModeProvider } from "./ThemeModeProvider";

// Mocks only fetch, driving the real inventoryService hook, matching
// TablesPage.test.tsx's established pattern.

const WAREHOUSE_MANAGER: CurrentUser = {
  id: 1,
  username: "noa",
  full_name: "Noa Cohen",
  role: "warehouse_manager",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const WAITER: CurrentUser = {
  id: 2,
  username: "maya",
  full_name: "Maya Levi",
  role: "waiter",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const LOW_INGREDIENT = {
  id: 1,
  name: "Basil",
  unit: "kg",
  current_stock: "0.500",
  min_stock_threshold: "2.000",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

/**
 * A minimal stand-in for the browser's WebSocket, copied from
 * TablesPage.test.tsx (continuing the existing per-test-file-copy precedent).
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

function jsonResponse(status: number, body: unknown): Response {
  const text = JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(text),
    json: () => Promise.resolve(JSON.parse(text)),
  } as unknown as Response;
}

function renderShell(user: CurrentUser) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeModeProvider>
        <MemoryRouter>
          <RealtimeProvider>
            <AppShell user={user} />
          </RealtimeProvider>
        </MemoryRouter>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("AppShell", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the Alerts nav badge with the active alert count for a warehouse_manager", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/inventory/alerts")) {
          return Promise.resolve(jsonResponse(200, [LOW_INGREDIENT]));
        }
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );

    // Act
    renderShell(WAREHOUSE_MANAGER);

    // Assert
    expect(await screen.findByText("1")).toBeInTheDocument();
  });

  it("shows the Tables nav badge with the ready-order count for a waiter", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/orders")) {
          return Promise.resolve(
            jsonResponse(200, [
              { id: 1, table_id: 1, waiter_id: 2, status: "ready", created_at: "2026-01-01T00:00:00Z", closed_at: null, total_amount: null },
              { id: 2, table_id: 2, waiter_id: 2, status: "in_preparation", created_at: "2026-01-01T00:00:00Z", closed_at: null, total_amount: null },
            ]),
          );
        }
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );

    // Act
    renderShell(WAITER);

    // Assert
    expect(await screen.findByText("1")).toBeInTheDocument();
  });

  it("refetches the ready-order count when a live order.status_changed event arrives", async () => {
    // Arrange
    let openOrders: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/orders")) return Promise.resolve(jsonResponse(200, openOrders));
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );

    // Act
    renderShell(WAITER);
    await screen.findByText("Tables");
    openOrders = [
      { id: 1, table_id: 1, waiter_id: 2, status: "ready", created_at: "2026-01-01T00:00:00Z", closed_at: null, total_amount: null },
    ];
    const socket = FakeWebSocket.instances[0];
    expect(socket).toBeDefined();
    socket.onmessage?.({
      data: JSON.stringify({ event: "order.status_changed", payload: openOrders[0] }),
    });

    // Assert
    expect(await screen.findByText("1")).toBeInTheDocument();
  });

});
