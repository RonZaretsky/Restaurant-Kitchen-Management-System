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

/**
 * Routes a stubbed `fetch` to `/api/tables` and `/api/orders`, the two queries every
 * `TablesPage` render depends on. `openOrders` defaults to `[]` so a test that does not
 * care about the attention-state treatment does not need to think about it.
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
 * RealtimeProvider.test.tsx: TablesPage renders inside a RealtimeProvider,
 * which opens a real WebSocket on mount, and jsdom's real one attempts an
 * actual, slow, eventually-failing network connection.
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

});
