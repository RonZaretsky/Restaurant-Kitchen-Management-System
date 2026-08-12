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
        if (String(url).includes("/api/tables/")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE]));
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
        if (path.includes("/api/tables/") && init.method === "POST") {
          const body = JSON.parse(String(init.body));
          const created = { id: 5, table_number: body.table_number, capacity: body.capacity, status: "available" };
          tables = [...tables, created];
          return Promise.resolve(jsonResponse(201, created));
        }
        if (path.includes("/api/tables/")) return Promise.resolve(jsonResponse(200, tables));
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
        if (path.includes("/api/tables/") && init.method === "POST") {
          return Promise.resolve(jsonResponse(409, { detail: "Rejected, table number already exists" }));
        }
        if (path.includes("/api/tables/")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE]));
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
        if (String(url).includes("/api/tables/")) return Promise.resolve(jsonResponse(200, [OCCUPIED_TABLE]));
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
        if (path.includes("/api/tables/1") && init.method === "PATCH") {
          const body = JSON.parse(String(init.body));
          Object.assign(table, body);
          return Promise.resolve(jsonResponse(200, table));
        }
        if (path.includes("/api/tables/")) return Promise.resolve(jsonResponse(200, [table]));
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

  it("never issues a delete request and renders no delete affordance (AC7)", async () => {
    // Arrange
    const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
      void init;
      if (String(url).includes("/api/tables/")) return Promise.resolve(jsonResponse(200, [AVAILABLE_TABLE, OCCUPIED_TABLE]));
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
