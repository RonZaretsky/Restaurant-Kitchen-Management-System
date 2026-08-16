import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RealtimeProvider } from "../../components/shell/RealtimeProvider";
import { KitchenDisplayPage } from "./KitchenDisplayPage";

// Mocks only fetch, driving the real kitchenService/tableService/menuService
// hooks, matching TableOrderDetailPage.test.tsx's established pattern.

const TABLE_5 = { id: 1, table_number: 5, capacity: 4, status: "occupied" };
const TABLE_9 = { id: 2, table_number: 9, capacity: 2, status: "occupied" };

const DISH = {
  id: 7,
  name: "Shakshuka",
  description: null,
  price: "42.00",
  category_id: 1,
  is_available: true,
  prep_time_minutes: 10,
  created_at: "2026-01-01T00:00:00Z",
};

const ITEM_TABLE_5 = {
  id: 1,
  order_id: 10,
  table_id: 1,
  dish_id: 7,
  quantity: 2,
  status: "pending",
  notes: "no onions",
  cook_id: null,
  price_at_add: "42.00",
};

const ITEM_TABLE_9 = {
  id: 2,
  order_id: 11,
  table_id: 2,
  dish_id: 7,
  quantity: 1,
  status: "in_preparation",
  notes: null,
  cook_id: 3,
  price_at_add: "42.00",
};

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
 * TableOrderDetailPage.test.tsx (continuing the existing per-test-file-copy
 * precedent, see deferred-work.md's note on that call).
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

function stubReads(overrides: { items?: unknown[]; tables?: unknown[]; dishes?: unknown[] } = {}) {
  const items = overrides.items ?? [];
  const tables = overrides.tables ?? [TABLE_5, TABLE_9];
  const dishes = overrides.dishes ?? [DISH];
  return (url: string) => {
    const path = String(url);
    if (path.includes("/api/kitchen/items")) return Promise.resolve(jsonResponse(200, items));
    if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, tables));
    if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, dishes));
    return Promise.reject(new Error(`unexpected request: ${url}`));
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <RealtimeProvider>
        <KitchenDisplayPage />
      </RealtimeProvider>
    </QueryClientProvider>,
  );
}

describe("KitchenDisplayPage", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows 'No orders in the queue' when nothing is active", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads({ items: [] })));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No orders in the queue")).toBeInTheDocument();
  });

  it("groups items under their own Table's card, resolving dish name and table number", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads({ items: [ITEM_TABLE_5, ITEM_TABLE_9] })));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Table 5")).toBeInTheDocument();
    expect(screen.getByText("Table 9")).toBeInTheDocument();
    const shakshukaRows = screen.getAllByText("Shakshuka × 2");
    expect(shakshukaRows).toHaveLength(1);
    expect(screen.getByText("Shakshuka × 1")).toBeInTheDocument();
    expect(screen.getByText("no onions")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("In preparation")).toBeInTheDocument();
  });

  it("renders no action controls anywhere on the board", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads({ items: [ITEM_TABLE_5] })));

    // Act
    renderPage();
    await screen.findByText("Table 5");

    // Assert: this story is read-only, Story 5.2 adds pick-up/mark-ready.
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("shows a retry-capable error when any of the three underlying queries fails", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/kitchen/items")) return Promise.reject(new TypeError("Failed to fetch"));
        return stubReads()(url);
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText(/Could not load the kitchen display/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("adds a new item to its Table's card when a live order.item_added event arrives", async () => {
    // Arrange: starts with only Table 5's item, then the backend reports a
    // second item on Table 9 once the WebSocket event lands.
    let items: unknown[] = [ITEM_TABLE_5];
    vi.stubGlobal("fetch", vi.fn((url: string) => stubReads({ items })(url)));

    // Act
    renderPage();
    await screen.findByText("Table 5");
    expect(screen.queryByText("Table 9")).not.toBeInTheDocument();
    items = [ITEM_TABLE_5, ITEM_TABLE_9];
    const socket = FakeWebSocket.instances[0];
    expect(socket).toBeDefined();
    socket.onmessage?.({
      data: JSON.stringify({ event: "order.item_added", payload: ITEM_TABLE_9 }),
    });

    // Assert
    expect(await screen.findByText("Table 9")).toBeInTheDocument();
  });

  it("resolves a table created after the initial load once a live event refetches the tables list", async () => {
    // Arrange: TABLE_9 is deliberately absent from the initial /api/tables
    // response (simulating it being created after this page's own query
    // already resolved); it only appears once the live event triggers a
    // TABLES_QUERY_KEY refetch (review finding, Story 5.1).
    let items: unknown[] = [];
    let tables: unknown[] = [TABLE_5];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => stubReads({ items, tables })(url)),
    );

    // Act
    renderPage();
    await screen.findByText("No orders in the queue");
    items = [ITEM_TABLE_9];
    tables = [TABLE_5, TABLE_9];
    const socket = FakeWebSocket.instances[0];
    expect(socket).toBeDefined();
    socket.onmessage?.({
      data: JSON.stringify({ event: "order.item_added", payload: ITEM_TABLE_9 }),
    });

    // Assert: resolves to the real table_number, not the "?" fallback.
    expect(await screen.findByText("Table 9")).toBeInTheDocument();
    expect(screen.queryByText("Table ?")).not.toBeInTheDocument();
  });
});
