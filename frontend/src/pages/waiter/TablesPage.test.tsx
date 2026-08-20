import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RealtimeProvider } from "../../components/shell/RealtimeProvider";
import { TablesPage } from "./TablesPage";

// Mocks only fetch, driving the real tableService/orderService hooks,
// matching TablesSetupPage.test.tsx's established pattern.

const AVAILABLE_TABLE = { id: 1, table_number: 1, capacity: 4, status: "available" };
const OCCUPIED_TABLE = { id: 2, table_number: 2, capacity: 2, status: "occupied" };
const RESERVED_TABLE = { id: 3, table_number: 3, capacity: 6, status: "reserved" };

function readyOrder(tableId: number) {
  return {
    id: 100 + tableId,
    table_id: tableId,
    waiter_id: 1,
    status: "ready",
    created_at: "2026-01-01T00:00:00Z",
    closed_at: null,
    total_amount: "12.50",
  };
}

/**
 * Routes a stubbed `fetch` to `/api/tables` and `/api/orders`, the two queries every
 * `TablesPage` render now depends on (Story 5.3). `openOrders` defaults to `[]` so existing
 * tests that don't care about the attention-state treatment don't need to think about it.
 */
function stubTablesAndOrders(tables: unknown[], openOrders: unknown[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const path = String(url);
      if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, tables));
      if (path.includes("/api/orders")) return Promise.resolve(jsonResponse(200, openOrders));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    }),
  );
}

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
 * RealtimeProvider.test.tsx (Story 3.3): TablesPage now renders inside a
 * RealtimeProvider, which opens a real WebSocket on mount, and jsdom's real
 * one attempts an actual, slow, eventually-failing network connection.
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
          <TablesPage />
        </RealtimeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TablesPage", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    navigateMock.mockClear();
  });

  it("renders every table with its status badge", async () => {
    // Arrange
    stubTablesAndOrders([AVAILABLE_TABLE, OCCUPIED_TABLE, RESERVED_TABLE]);

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Table 1")).toBeInTheDocument();
    expect(screen.getByText("available")).toBeInTheDocument();
    expect(screen.getByText("Table 2")).toBeInTheDocument();
    expect(screen.getByText("occupied")).toBeInTheDocument();
    expect(screen.getByText("Table 3")).toBeInTheDocument();
    expect(screen.getByText("reserved")).toBeInTheDocument();
  });

  it("opens an available table and navigates to its detail page on success", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/orders/tables/1/open") && init.method === "POST") {
          return Promise.resolve(
            jsonResponse(201, {
              id: 10,
              table_id: 1,
              waiter_id: 2,
              status: "pending",
              created_at: "2026-01-01T00:00:00Z",
              closed_at: null,
              total_amount: null,
            }),
          );
        }
        if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE]));
        if (path.includes("/api/orders")) return Promise.resolve(jsonResponse(200, []));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByText("Table 1"));

    // Assert
    await vi.waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/waiter/tables/1"));
  });

  it("shows an inline error and does not navigate when the open request is rejected", async () => {
    // Arrange: the table was available when this client fetched it but lost the
    // open race, so the backend answers 409.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/orders/tables/1/open") && init.method === "POST") {
          return Promise.resolve(jsonResponse(409, { detail: "Rejected, table not available" }));
        }
        if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE]));
        if (path.includes("/api/orders")) return Promise.resolve(jsonResponse(200, []));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByText("Table 1"));

    // Assert
    expect(await screen.findByText("Rejected, table not available")).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("navigates straight to the detail page on an occupied tile, without opening it", async () => {
    // Arrange
    const fetchMock = vi.fn((url: string) => {
      const path = String(url);
      if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, [OCCUPIED_TABLE]));
      if (path.includes("/api/orders")) return Promise.resolve(jsonResponse(200, []));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByText("Table 2"));

    // Assert: no open request was ever issued, just a straight navigation.
    expect(fetchMock.mock.calls.every(([url]) => !String(url).includes("/open"))).toBe(true);
    expect(navigateMock).toHaveBeenCalledWith("/waiter/tables/2");
  });

  it("has no click affordance on a reserved tile", async () => {
    // Arrange
    const fetchMock = vi.fn((url: string) => {
      const path = String(url);
      if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, [RESERVED_TABLE]));
      if (path.includes("/api/orders")) return Promise.resolve(jsonResponse(200, []));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByText("Table 3"));

    // Assert
    expect(fetchMock.mock.calls.every(([url]) => !String(url).includes("/open"))).toBe(true);
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("shows the empty-state copy when there are no tables", async () => {
    // Arrange
    stubTablesAndOrders([]);

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No tables configured yet.")).toBeInTheDocument();
  });

  it("refetches the table list when a live table.status_changed event arrives", async () => {
    // Arrange: the list starts as one available table, then the backend
    // reports it occupied on the second fetch, simulating another Waiter's
    // concurrent open (Story 3.3, AC2/AC3).
    let tables = [AVAILABLE_TABLE];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, tables));
        if (path.includes("/api/orders")) return Promise.resolve(jsonResponse(200, []));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();
    await screen.findByText("available");
    tables = [{ ...AVAILABLE_TABLE, status: "occupied" }];
    const socket = FakeWebSocket.instances[0];
    expect(socket).toBeDefined();
    socket.onmessage?.({
      data: JSON.stringify({ event: "table.status_changed", payload: { table_id: 1, status: "occupied" } }),
    });

    // Assert
    expect(await screen.findByText("occupied")).toBeInTheDocument();
  });

  it("shows the attention-state chip on an occupied tile whose Order is ready, layered on the status badge", async () => {
    // Arrange
    stubTablesAndOrders([OCCUPIED_TABLE], [readyOrder(OCCUPIED_TABLE.id)]);

    // Act
    renderPage();

    // Assert: both the base table-status Chip and the new attention Chip render, the base one
    // is not replaced (DESIGN.md's "layered on top of, not replacing" instruction).
    expect(await screen.findByText("occupied")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });

  it("does not show the attention-state chip when the occupied tile's Order is not ready", async () => {
    // Arrange
    const inPreparationOrder = { ...readyOrder(OCCUPIED_TABLE.id), status: "in_preparation" };
    stubTablesAndOrders([OCCUPIED_TABLE], [inPreparationOrder]);

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("occupied")).toBeInTheDocument();
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
  });

  it("never shows the attention-state chip on an available or reserved tile", async () => {
    // Arrange: a ready Order can only ever belong to an occupied Table in v1 (no
    // reservation-arrival flow), but this asserts the tile itself never renders the chip for a
    // non-occupied status regardless of what the open-orders list happens to contain.
    stubTablesAndOrders(
      [AVAILABLE_TABLE, RESERVED_TABLE],
      [readyOrder(AVAILABLE_TABLE.id), readyOrder(RESERVED_TABLE.id)],
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("available")).toBeInTheDocument();
    expect(screen.getByText("reserved")).toBeInTheDocument();
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
  });

  it("refetches the open-orders list when a live order.status_changed event arrives", async () => {
    // Arrange: the occupied tile starts with no ready Order, then the backend reports one on
    // the second fetch, simulating a Cook marking the last item ready (Story 5.3, AC4).
    let openOrders: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, [OCCUPIED_TABLE]));
        if (path.includes("/api/orders")) return Promise.resolve(jsonResponse(200, openOrders));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();
    await screen.findByText("occupied");
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
    openOrders = [readyOrder(OCCUPIED_TABLE.id)];
    const socket = FakeWebSocket.instances[0];
    expect(socket).toBeDefined();
    socket.onmessage?.({
      data: JSON.stringify({ event: "order.status_changed", payload: { id: 101, status: "ready" } }),
    });

    // Assert
    expect(await screen.findByText("Ready")).toBeInTheDocument();
  });

  it("shows a retry-capable error when the table list cannot be loaded", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText(/Could not load the tables/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("retries the open-orders query too when only it failed, not just the table list", async () => {
    // Arrange: tables loads fine on the first try; open-orders fails once, then succeeds on
    // retry (code review finding, Story 5.3: Retry previously only refetched useTables(), so a
    // failure isolated to useOpenOrders() left the page stuck behind the error banner forever).
    let openOrdersAttempts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, [OCCUPIED_TABLE]));
        if (path.includes("/api/orders")) {
          openOrdersAttempts += 1;
          if (openOrdersAttempts === 1) return Promise.reject(new TypeError("Failed to fetch"));
          return Promise.resolve(jsonResponse(200, []));
        }
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText(/Could not load the tables/);
    await user.click(screen.getByRole("button", { name: "Retry" }));

    // Assert: the retried open-orders request succeeds and the grid renders.
    expect(await screen.findByText("occupied")).toBeInTheDocument();
  });
});
