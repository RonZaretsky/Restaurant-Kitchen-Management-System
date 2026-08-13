import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TablesSetupPage } from "./TablesSetupPage";

// Mocks only fetch, driving the real tableService hooks, matching
// appIntegration.test.tsx's pattern (Story 1.4's lesson, reapplied by Story
// 2.3's review): mocking the service itself would hide the
// invalidate-and-refetch wiring between a mutation and the list.

const AVAILABLE_TABLE = { id: 1, table_number: 1, capacity: 4, status: "available" };
const OCCUPIED_TABLE = { id: 2, table_number: 2, capacity: 2, status: "occupied" };

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
      <TablesSetupPage />
    </QueryClientProvider>,
  );
}

describe("TablesSetupPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the table list from the backend", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/tables")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE]));
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("1")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("available")).toBeInTheDocument();
  });

  it("creates a table and shows it in the list once the mutation resolves", async () => {
    // Arrange
    let tables: Array<typeof AVAILABLE_TABLE> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/tables") && init.method === "POST") {
          const body = JSON.parse(String(init.body));
          const created = { id: 5, table_number: body.table_number, capacity: body.capacity, status: "available" };
          tables = [...tables, created];
          return Promise.resolve(jsonResponse(201, created));
        }
        if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, tables));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    expect(await screen.findByText("No tables configured yet.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Table number"), "9");
    await user.type(screen.getByLabelText("Capacity (seats)"), "6");
    await user.click(screen.getByRole("button", { name: "Add table" }));

    // Assert
    expect(await screen.findByText("9")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
  });

  it("surfaces the backend's exact duplicate-number message inline", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/tables") && init.method === "POST") {
          return Promise.resolve(jsonResponse(409, { detail: "Rejected, table number already exists" }));
        }
        if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("available");
    await user.type(screen.getByLabelText("Table number"), "1");
    await user.type(screen.getByLabelText("Capacity (seats)"), "4");
    await user.click(screen.getByRole("button", { name: "Add table" }));

    // Assert
    expect(await screen.findByText("Rejected, table number already exists")).toBeInTheDocument();
  });

  it("disables Edit and shows the in-use reason for an occupied table", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/tables")) return Promise.resolve(jsonResponse(200, [OCCUPIED_TABLE]));
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );

    // Act
    renderPage();

    // Assert: the reason is visible text, not only a Tooltip title, so it is
    // findable without hover/focus.
    expect(await screen.findByRole("button", { name: "Edit" })).toBeDisabled();
    expect(screen.getByText("Rejected, table in use")).toBeInTheDocument();
  });

  it("edits an available table and exits edit mode on success", async () => {
    // Arrange
    const table = { ...AVAILABLE_TABLE };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.endsWith("/api/tables/1") && init.method === "PATCH") {
          const body = JSON.parse(String(init.body));
          Object.assign(table, body);
          return Promise.resolve(jsonResponse(200, table));
        }
        if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, [table]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const capacityField = screen.getByLabelText("Capacity for table 1");
    await user.clear(capacityField);
    await user.type(capacityField, "8");
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert: edit mode exits and the new value renders as plain text.
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument());
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  it("shows an error with a retry when the table list cannot be loaded", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText(/Could not load the tables/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });


  it("surfaces a rejected row edit inline with the backend's exact message (AC5)", async () => {
    // Arrange: the rename-to-duplicate rejection has to reach the Admin with the
    // same copy the create path uses, and only the create half was proven before.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.endsWith("/api/tables/1") && init.method === "PATCH") {
          return Promise.resolve(jsonResponse(409, { detail: "Rejected, table number already exists" }));
        }
        if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const numberField = screen.getByLabelText("Table number for table 1");
    await user.clear(numberField);
    await user.type(numberField, "2");
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert
    expect(await screen.findByText("Rejected, table number already exists")).toBeInTheDocument();
  });

  it("blocks a save when a field is not a positive whole number", async () => {
    // Arrange: Number("abc") is NaN and JSON.stringify turns NaN into null, which
    // the backend would otherwise read as "field omitted" and half-apply.
    const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
      void init;
      if (String(url).includes("/api/tables")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE]));
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const numberField = screen.getByLabelText("Table number for table 1");
    await user.clear(numberField);
    await user.type(numberField, "abc");

    // Assert
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByText("Enter a whole number greater than zero")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PATCH")).toBe(false);
  });

  it("always sends both fields, so an edit matching a stale cached value still saves", async () => {
    // Arrange: diffing the drafts against the cached row means typing the cached
    // value produces an empty payload, no request, and a row that looks saved
    // while the server holds something else.
    const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
      const path = String(url);
      if (path.endsWith("/api/tables/1") && init.method === "PATCH") {
        return Promise.resolve(jsonResponse(200, AVAILABLE_TABLE));
      }
      if (path.includes("/api/tables")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE]));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act: save without changing anything the client can see.
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Assert: a request still goes out, carrying both fields.
    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === "PATCH");
      expect(patch).toBeDefined();
      expect(JSON.parse(String((patch![1] as RequestInit).body))).toEqual({
        table_number: 1,
        capacity: 4,
      });
    });
  });

  it("leaves edit mode when the table is seated by someone else", async () => {
    // Arrange: the row starts available and editable, then a refetch reports it
    // occupied. Staying in edit mode would leave a form whose next Save can only
    // 409, with the in-use reason suppressed.
    let current: Record<string, unknown> = { ...AVAILABLE_TABLE };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        void init;
        if (String(url).includes("/api/tables")) return Promise.resolve(jsonResponse(200, [current]));
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    const { rerender } = renderPage();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    current = { ...AVAILABLE_TABLE, status: "occupied" };
    rerender(<></>);

    // Assert
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument());
  });

  it("never issues a delete request and renders no delete affordance (AC7)", async () => {
    // Arrange
    const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
      void init;
      if (String(url).includes("/api/tables")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE, OCCUPIED_TABLE]));
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    // Act
    renderPage();
    await screen.findByText("available");

    // Assert
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "DELETE")).toBe(false);
  });
});
