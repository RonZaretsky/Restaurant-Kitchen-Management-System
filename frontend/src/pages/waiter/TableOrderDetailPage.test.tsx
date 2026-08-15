import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RealtimeProvider } from "../../components/shell/RealtimeProvider";
import { TableOrderDetailPage } from "./TableOrderDetailPage";

// Mocks only fetch, driving the real orderService/menuService/tableService hooks,
// matching TablesPage.test.tsx's established pattern.

// table_number deliberately differs from id: the heading must show the number a
// waiter reads off the tile, not the row's primary key.
const TABLE = { id: 1, table_number: 12, capacity: 4, status: "occupied" };

const ORDER = {
  id: 10,
  table_id: 1,
  waiter_id: 2,
  status: "pending",
  created_at: "2026-01-01T00:00:00Z",
  closed_at: null,
  total_amount: null,
};

const DISHES = [
  {
    id: 5,
    name: "Shakshuka",
    description: null,
    price: "42.00",
    category_id: 1,
    is_available: true,
    prep_time_minutes: 10,
    created_at: "2026-01-01T00:00:00Z",
  },
];

const PENDING_ITEM = {
  id: 1,
  order_id: 10,
  dish_id: 5,
  quantity: 1,
  status: "pending",
  notes: null,
  cook_id: null,
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
 * Answers every read this page makes, so each test only has to describe what it
 * changes. Order matters: /api/orders/tables/1 must be matched before /api/tables.
 */
function stubReads(overrides: {
  order?: Response;
  items?: unknown;
  dishes?: unknown;
  tables?: unknown;
} = {}) {
  return (url: string, _init: RequestInit = {}) => {
    const path = String(url);
    if (path.includes("/api/orders/tables/")) {
      return Promise.resolve(overrides.order ?? jsonResponse(200, ORDER));
    }
    if (path.includes("/api/orders/") && path.includes("/items")) {
      return Promise.resolve(jsonResponse(200, overrides.items ?? []));
    }
    if (path.includes("/api/menu/dishes")) {
      return Promise.resolve(jsonResponse(200, overrides.dishes ?? DISHES));
    }
    if (path.includes("/api/tables")) {
      return Promise.resolve(jsonResponse(200, overrides.tables ?? [TABLE]));
    }
    return Promise.reject(new Error(`unexpected request: ${path}`));
  };
}

/**
 * A minimal stand-in for the browser's WebSocket, copied from
 * RealtimeProvider.test.tsx (Story 3.3): this page now renders inside a
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

function renderPage(initialPath = "/waiter/tables/1") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <RealtimeProvider>
          <Routes>
            <Route path="/waiter/tables/:tableId" element={<TableOrderDetailPage />} />
          </Routes>
        </RealtimeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TableOrderDetailPage", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("heads the page with the table's number, not its database id", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads()));

    // Act
    renderPage();

    // Assert: TABLE.id is 1 and TABLE.table_number is 12.
    expect(await screen.findByRole("heading", { name: "Table 12" })).toBeInTheDocument();
  });

  it("shows the empty-state copy when the order has no items", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads()));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No items added yet.")).toBeInTheDocument();
  });

  it("renders each order item's status badge, dish name, note, quantity, and price", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads({ items: [PENDING_ITEM] })));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Shakshuka")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("42.00 ₪")).toBeInTheDocument();
  });

  it("renders an em dash for a note that is present but blank", async () => {
    // Arrange: the API can return "" or whitespace, which ?? would let through.
    vi.stubGlobal("fetch", vi.fn(stubReads({ items: [{ ...PENDING_ITEM, notes: "   " }] })));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("—")).toBeInTheDocument();
  });

  it("submits exactly what was entered and shows the new item in the list", async () => {
    // Arrange: the mock echoes the submitted body back rather than hardcoding it,
    // so a page that posted the wrong dish, quantity, or note would fail here.
    let items: Array<Record<string, unknown>> = [];
    let submitted: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/orders/") && path.includes("/items") && init.method === "POST") {
          submitted = JSON.parse(String(init.body));
          const newItem = { ...PENDING_ITEM, id: items.length + 1, ...submitted };
          items = [...items, newItem];
          return Promise.resolve(jsonResponse(201, newItem));
        }
        return stubReads({ items })(url);
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("combobox", { name: "Dish" }));
    await user.click(await screen.findByRole("option", { name: "Shakshuka" }));
    await user.clear(screen.getByLabelText("Qty"));
    await user.type(screen.getByLabelText("Qty"), "3");
    await user.type(screen.getByLabelText("Note (optional)"), "no onions");
    await user.click(screen.getByRole("button", { name: "Add to order" }));

    // Assert
    expect(await screen.findByText("no onions")).toBeInTheDocument();
    expect(submitted).toEqual({ dish_id: 5, quantity: 3, notes: "no onions" });
  });

  it("shows the inline rejection message when the dish is unavailable", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/orders/") && path.includes("/items") && init.method === "POST") {
          return Promise.resolve(jsonResponse(409, { detail: "Rejected, dish unavailable" }));
        }
        return stubReads()(url);
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("combobox", { name: "Dish" }));
    await user.click(await screen.findByRole("option", { name: "Shakshuka" }));
    await user.click(screen.getByRole("button", { name: "Add to order" }));

    // Assert
    expect(await screen.findByText("Rejected, dish unavailable")).toBeInTheDocument();
  });

  it("refuses a quantity above the cap without sending it to the server", async () => {
    // Arrange
    const fetchMock = vi.fn(stubReads());
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("combobox", { name: "Dish" }));
    await user.click(await screen.findByRole("option", { name: "Shakshuka" }));
    await user.clear(screen.getByLabelText("Qty"));
    await user.type(screen.getByLabelText("Qty"), "100");

    // Assert: the reason is visible, and no POST was ever attempted.
    expect(await screen.findAllByText("Enter a whole number from 1 to 99")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Add to order" })).toBeDisabled();
    expect(
      fetchMock.mock.calls.every(([, init]) => (init as RequestInit)?.method !== "POST"),
    ).toBe(true);
  });

  it("presents a table with no open order as its own state, not a failed request", async () => {
    // Arrange: reachable by typing the URL of an available table.
    vi.stubGlobal(
      "fetch",
      vi.fn(stubReads({ order: jsonResponse(404, { detail: "Order not found" }) })),
    );

    // Act
    renderPage();

    // Assert: no Retry button, since retrying could never succeed.
    expect(await screen.findByText(/This table has no open order/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("rejects a non-numeric table id without requesting a malformed url", async () => {
    // Arrange
    const fetchMock = vi.fn(stubReads());
    vi.stubGlobal("fetch", fetchMock);

    // Act
    renderPage("/waiter/tables/abc");

    // Assert: no "Table NaN" heading, and no order lookup was attempted. The
    // dish/table list reads still fire (hooks cannot be called conditionally),
    // but they are well-formed requests, unlike /api/orders/tables/NaN.
    expect(await screen.findByText(/That table link is not valid/)).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/orders/"))).toBe(false);
  });

  it("tells the waiter when there is nothing on the menu to add", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads({ dishes: [] })));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText(/No dishes on the menu yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add to order" })).not.toBeInTheDocument();
  });

  it("refetches the item list when a live order.item_added event arrives", async () => {
    // Arrange: the item list starts empty, then the backend reports one item
    // on the second fetch, simulating another Waiter's concurrent add (Story
    // 3.3, AC2/AC3).
    let items: unknown[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string) => stubReads({ items })(url)));

    // Act
    renderPage();
    await screen.findByText("No items added yet.");
    items = [PENDING_ITEM];
    const socket = FakeWebSocket.instances[0];
    expect(socket).toBeDefined();
    socket.onmessage?.({ data: JSON.stringify({ event: "order.item_added", payload: PENDING_ITEM }) });

    // Assert
    expect(await screen.findByText("Shakshuka")).toBeInTheDocument();
  });

  it("shows a retry-capable error when the order cannot be loaded", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText(/Could not load the order/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
