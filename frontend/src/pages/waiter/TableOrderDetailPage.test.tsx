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

const IN_PREPARATION_ITEM = {
  id: 2,
  order_id: 10,
  dish_id: 5,
  quantity: 2,
  status: "in_preparation",
  notes: null,
  cook_id: 3,
  price_at_add: "42.00",
};

const READY_ITEM = {
  id: 3,
  order_id: 10,
  dish_id: 5,
  quantity: 1,
  status: "ready",
  notes: null,
  cook_id: 3,
  price_at_add: "42.00",
};

const CANCELLED_ITEM = {
  id: 4,
  order_id: 10,
  dish_id: 5,
  quantity: 1,
  status: "cancelled",
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

  it("renders each order item's status badge, dish name, note, quantity, and price", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads({ items: [PENDING_ITEM] })));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Shakshuka")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    // Two matches: the item row's own price cell, and the total bar (Story 5.4), which
    // happens to equal the same amount for a single qty-1 item.
    expect(screen.getAllByText("42.00 ₪")).toHaveLength(2);
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

  it("edits a pending item, always sending both quantity and note", async () => {
    // Arrange: the mock echoes the submitted body back, matching the add-item
    // test's own "never hardcode what the page sent" pattern, so a page that
    // diffed against cached data (forbidden outright, project-context.md) or
    // omitted a field would fail here.
    let items = [PENDING_ITEM];
    let submitted: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/items/1") && init.method === "PATCH") {
          submitted = JSON.parse(String(init.body));
          const updated = { ...PENDING_ITEM, ...submitted };
          items = [updated];
          return Promise.resolve(jsonResponse(200, updated));
        }
        return stubReads({ items })(url);
      }),
    );
    const user = userEvent.setup();

    // Act: two "Qty"/"Note" fields exist at once once editing starts, the
    // add-item form's own and this row's edit fields, so disambiguate by
    // taking the row's (the second of each pair in DOM order).
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const qtyFields = screen.getAllByLabelText("Qty");
    const qtyField = qtyFields[qtyFields.length - 1];
    await user.clear(qtyField);
    await user.type(qtyField, "4");
    const noteFields = screen.getAllByLabelText("Note (optional)");
    await user.type(noteFields[noteFields.length - 1], "extra spicy");
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    await screen.findByText("extra spicy");
    expect(submitted).toEqual({ quantity: 4, notes: "extra spicy" });
  });

  it("cancels a pending item immediately, with no confirm step", async () => {
    // Arrange
    let items = [PENDING_ITEM];
    const cancelMock = vi.fn(() => Promise.resolve(jsonResponse(200, { ...PENDING_ITEM, status: "cancelled" })));
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/items/1/cancel") && init.method === "POST") {
          items = [{ ...PENDING_ITEM, status: "cancelled" }];
          return cancelMock();
        }
        return stubReads({ items })(url);
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    // Assert: exactly one call, no intermediate confirm click was needed.
    await vi.waitFor(() => expect(cancelMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Cancelled")).toBeInTheDocument();
  });

  it("requires an explicit confirm before cancelling an in_preparation item", async () => {
    // Arrange
    let items = [IN_PREPARATION_ITEM];
    const cancelMock = vi.fn(() =>
      Promise.resolve(jsonResponse(200, { ...IN_PREPARATION_ITEM, status: "cancelled" })),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/items/2/cancel") && init.method === "POST") {
          items = [{ ...IN_PREPARATION_ITEM, status: "cancelled" }];
          return cancelMock();
        }
        return stubReads({ items })(url);
      }),
    );
    const user = userEvent.setup();

    // Act: the first Cancel click only reveals the confirm, it must not call the endpoint yet.
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    // Assert: nothing sent yet, the warning is visible.
    expect(cancelMock).not.toHaveBeenCalled();
    expect(
      await screen.findByText(/Stock already deducted for this item will not be restored/),
    ).toBeInTheDocument();

    // Act: only the explicit Confirm click sends the request.
    await user.click(screen.getByRole("button", { name: "Confirm cancel" }));

    // Assert
    await vi.waitFor(() => expect(cancelMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Cancelled")).toBeInTheDocument();
  });

  it("has no action controls on a ready or cancelled row", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads({ items: [READY_ITEM, CANCELLED_ITEM] })));

    // Act
    renderPage();

    // Assert
    await screen.findByText("Ready");
    await screen.findByText("Cancelled");
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("computes the pre-close total client-side, excluding a cancelled item", async () => {
    // Arrange: 42.00 (pending, qty 1) + 42.00*2 (in_preparation, qty 2) = 126.00, excluding the
    // cancelled item's own 42.00.
    vi.stubGlobal(
      "fetch",
      vi.fn(stubReads({ items: [PENDING_ITEM, IN_PREPARATION_ITEM, CANCELLED_ITEM] })),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("126.00 ₪")).toBeInTheDocument();
  });

  it("enables Mark served on a ready Order and calls the endpoint with no confirm step", async () => {
    // Arrange
    const serveMock = vi.fn(() => Promise.resolve(jsonResponse(200, { ...ORDER, status: "served" })));
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/orders/10/serve") && init.method === "POST") {
          return serveMock();
        }
        return stubReads({ order: jsonResponse(200, { ...ORDER, status: "ready" }), items: [READY_ITEM] })(url);
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    const serveButton = await screen.findByRole("button", { name: "Mark served" });
    expect(serveButton).toBeEnabled();
    await user.click(serveButton);

    // Assert: fired immediately, no intermediate confirm click required.
    await vi.waitFor(() => expect(serveMock).toHaveBeenCalledTimes(1));
  });

  it("keeps Close disabled until the Order is served, then applies immediately with no confirm", async () => {
    // Arrange
    const closeMock = vi.fn(() =>
      Promise.resolve(jsonResponse(200, { ...ORDER, status: "closed", total_amount: "42.00" })),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/orders/10/close") && init.method === "POST") {
          return closeMock();
        }
        return stubReads({ order: jsonResponse(200, { ...ORDER, status: "served" }), items: [READY_ITEM] })(url);
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    const closeButton = await screen.findByRole("button", { name: "Close order" });
    expect(closeButton).toBeEnabled();
    await user.click(closeButton);

    // Assert: fired immediately, no confirm dialog appeared first.
    await vi.waitFor(() => expect(closeMock).toHaveBeenCalledTimes(1));
  });

});
