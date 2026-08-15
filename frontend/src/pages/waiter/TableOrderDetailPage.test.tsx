import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TableOrderDetailPage } from "./TableOrderDetailPage";

// Mocks only fetch, driving the real orderService/menuService hooks, matching
// TablesPage.test.tsx's established pattern.

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

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/waiter/tables/1"]}>
        <Routes>
          <Route path="/waiter/tables/:tableId" element={<TableOrderDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TableOrderDetailPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the empty-state copy when the order has no items", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/orders/tables/1")) return Promise.resolve(jsonResponse(200, ORDER));
        if (path.includes("/api/orders/10/items")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, DISHES));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No items added yet.")).toBeInTheDocument();
  });

  it("renders each order item's status badge, dish name, note, quantity, and price", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/orders/tables/1")) return Promise.resolve(jsonResponse(200, ORDER));
        if (path.includes("/api/orders/10/items")) return Promise.resolve(jsonResponse(200, [PENDING_ITEM]));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, DISHES));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Shakshuka")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("42.00")).toBeInTheDocument();
  });

  it("submits the add-dish form and the new item appears in the list", async () => {
    // Arrange
    let items: Array<Record<string, unknown>> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/orders/tables/1")) return Promise.resolve(jsonResponse(200, ORDER));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, DISHES));
        if (path.includes("/api/orders/10/items") && init.method === "POST") {
          const newItem = { ...PENDING_ITEM, id: items.length + 1, notes: "no onions" };
          items = [...items, newItem];
          return Promise.resolve(jsonResponse(201, newItem));
        }
        if (path.includes("/api/orders/10/items")) return Promise.resolve(jsonResponse(200, items));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("combobox", { name: "Dish" }));
    await user.click(await screen.findByRole("option", { name: "Shakshuka" }));
    await user.type(screen.getByLabelText("Note (optional)"), "no onions");
    await user.click(screen.getByRole("button", { name: "Add to order" }));

    // Assert
    expect(await screen.findByText("no onions")).toBeInTheDocument();
  });

  it("shows the inline rejection message when the dish is unavailable", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/orders/tables/1")) return Promise.resolve(jsonResponse(200, ORDER));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, DISHES));
        if (path.includes("/api/orders/10/items") && init.method === "POST") {
          return Promise.resolve(jsonResponse(409, { detail: "Rejected, dish unavailable" }));
        }
        if (path.includes("/api/orders/10/items")) return Promise.resolve(jsonResponse(200, []));
        return Promise.reject(new Error(`unexpected request: ${path}`));
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
