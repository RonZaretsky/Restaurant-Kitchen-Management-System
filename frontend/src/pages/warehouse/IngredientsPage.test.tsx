import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IngredientsPage } from "./IngredientsPage";

// Mocks only fetch, driving the real inventoryService hooks, matching
// TablesSetupPage.test.tsx's pattern: mocking the service itself would hide
// the invalidate-and-refetch wiring between the create mutation and the list.

// Rows now navigate to the Ingredient detail page (Story 4.1), so useNavigate
// needs a mock, matching TablesPage.test.tsx's own precedent for the same shape.
const navigateMock = vi.fn();
vi.mock("react-router", async () => {
  const actual = await vi.importActual<typeof import("react-router")>("react-router");
  return { ...actual, useNavigate: () => navigateMock };
});

const FLOUR = {
  id: 1,
  name: "Flour",
  unit: "kg",
  current_stock: "10.000",
  min_stock_threshold: "1.000",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
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
  // queryClient is returned so a test can drive a refetch directly, which is
  // the only way to reach the "stale data present AND isError" state.
  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <IngredientsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
    queryClient,
  };
}

describe("IngredientsPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    navigateMock.mockClear();
  });

  it("renders the ingredient list from the backend", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/inventory/alerts")) return Promise.resolve(jsonResponse(200, []));
        if (String(url).includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR]));
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Flour")).toBeInTheDocument();
    expect(screen.getByText("kg")).toBeInTheDocument();
    expect(screen.getByText("10.000")).toBeInTheDocument();
    expect(screen.getByText("1.000")).toBeInTheDocument();
  });

  it("navigates to the Ingredient detail page when a row is clicked", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/inventory/alerts")) return Promise.resolve(jsonResponse(200, []));
        if (String(url).includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR]));
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByText("Flour"));

    // Assert
    expect(navigateMock).toHaveBeenCalledWith("/warehouse/ingredients/1");
  });

  it("shows the empty state instead of the old placeholder", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/inventory/alerts")) return Promise.resolve(jsonResponse(200, []));
        if (String(url).includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, []));
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );

    // Act
    renderPage();

    // Assert: AC3's exact required copy.
    expect(await screen.findByText("No ingredients recorded yet")).toBeInTheDocument();
  });

  it("creates an ingredient and shows it in the list once the mutation resolves", async () => {
    // Arrange: the mock's own state tracks created ingredients, so the GET
    // issued after the POST's cache invalidation reflects the addition.
    let ingredients: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
      const path = String(url);
      if (path.includes("/api/inventory/ingredients") && init.method === "POST") {
        const body = JSON.parse(String(init.body));
        const created = {
          id: 5,
          name: body.name,
          unit: body.unit,
          min_stock_threshold: body.min_stock_threshold,
          current_stock: body.current_stock ?? "0",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        };
        ingredients = [...ingredients, created];
        return Promise.resolve(jsonResponse(201, created));
      }
      if (path.includes("/api/inventory/alerts")) return Promise.resolve(jsonResponse(200, []));
      if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, ingredients));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    expect(await screen.findByText("No ingredients recorded yet")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Ingredient name"), "Sugar");
    await user.click(screen.getByRole("combobox", { name: "Unit" }));
    await user.click(await screen.findByRole("option", { name: "kg" }));
    await user.type(screen.getByLabelText("Minimum stock threshold"), "2");
    await user.click(screen.getByRole("button", { name: "Add ingredient" }));

    // Assert: appears in the list, form clears, and the optional current-stock
    // field that was left blank is omitted from the payload entirely.
    expect(await screen.findByText("Sugar")).toBeInTheDocument();
    // Every field the success handler clears, not just the first one.
    expect(screen.getByLabelText("Ingredient name")).toHaveValue("");
    expect(screen.getByLabelText("Minimum stock threshold")).toHaveValue("");
    expect(screen.getByLabelText("Current stock (optional)")).toHaveValue("");
    // MUI renders a zero-width-space placeholder in an empty select, so assert
    // the previously chosen label is gone rather than that the node is empty.
    expect(screen.getByRole("combobox", { name: "Unit" })).not.toHaveTextContent("kg");
    const post = fetchMock.mock.calls.find(
      ([reqUrl, reqInit]) =>
        String(reqUrl).includes("/api/inventory/ingredients") && (reqInit as RequestInit)?.method === "POST",
    );
    expect(post).toBeDefined();
    expect(JSON.parse(String((post![1] as RequestInit).body))).toEqual({
      name: "Sugar",
      unit: "kg",
      min_stock_threshold: "2",
    });
  });

  it("shows shortage styling immediately for a newly-created ingredient already below its own threshold", async () => {
    // Arrange: creating an Ingredient never goes through record_movement, so
    // nothing else would refresh the alerts list for it (Story 4.3 review
    // finding). useCreateIngredient must invalidate ALERTS_QUERY_KEY too, not
    // just INGREDIENTS_QUERY_KEY, or this row stays unstyled until an
    // unrelated event happens to refetch alerts.
    let ingredients: Array<Record<string, unknown>> = [];
    let alerts: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
      const path = String(url);
      if (path.includes("/api/inventory/ingredients") && init.method === "POST") {
        const body = JSON.parse(String(init.body));
        const created = {
          id: 9,
          name: body.name,
          unit: body.unit,
          min_stock_threshold: body.min_stock_threshold,
          current_stock: body.current_stock ?? "0",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        };
        ingredients = [...ingredients, created];
        // The backend's own derived /alerts list would include this new
        // ingredient immediately, since current_stock (0) < threshold (5).
        alerts = [...alerts, created];
        return Promise.resolve(jsonResponse(201, created));
      }
      if (path.includes("/api/inventory/alerts")) return Promise.resolve(jsonResponse(200, alerts));
      if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, ingredients));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    expect(await screen.findByText("No ingredients recorded yet")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Ingredient name"), "Rare Spice");
    await user.click(screen.getByRole("combobox", { name: "Unit" }));
    await user.click(await screen.findByRole("option", { name: "kg" }));
    await user.type(screen.getByLabelText("Minimum stock threshold"), "5");
    await user.click(screen.getByRole("button", { name: "Add ingredient" }));

    // Assert: the new row is styled as in-shortage without a manual reload.
    await screen.findByText("Rare Spice");
    const newRow = screen.getByText("Rare Spice").closest("tr");
    expect(newRow).not.toBeNull();
    expect(newRow!.querySelector('[data-testid="WarningAmberIcon"]')).toBeInTheDocument();
    expect(screen.getByText("Rare Spice")).toHaveStyle({ color: "rgb(211, 47, 47)" });
  });

  it("surfaces the exact duplicate-name message and preserves the form", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/inventory/ingredients") && init.method === "POST") {
          return Promise.resolve(jsonResponse(409, { detail: "That ingredient name already exists" }));
        }
        if (path.includes("/api/inventory/alerts")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("Flour");
    await user.type(screen.getByLabelText("Ingredient name"), "Flour");
    await user.click(screen.getByRole("combobox", { name: "Unit" }));
    await user.click(await screen.findByRole("option", { name: "kg" }));
    await user.type(screen.getByLabelText("Minimum stock threshold"), "1");
    await user.click(screen.getByRole("button", { name: "Add ingredient" }));

    // Assert: the backend's literal string, unrewritten, and the typed values stay.
    expect(await screen.findByText("That ingredient name already exists")).toBeInTheDocument();
    expect(screen.getByLabelText("Ingredient name")).toHaveValue("Flour");
  });

  it("shows an error with a working retry when the ingredient list cannot be loaded", async () => {
    // Arrange
    const fetchMock = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    expect(await screen.findByText(/Could not load the ingredients/)).toBeInTheDocument();

    // Assert: Retry actually refetches, rather than merely existing.
    const callsBeforeRetry = fetchMock.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBeforeRetry));
  });

  it("does not claim a count while the list is loading or failed", async () => {
    // Arrange: "0 ingredients" next to a load error states a fact about
    // inventory at the exact moment the page does not have one.
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));

    // Act
    renderPage();

    // Assert
    await screen.findByText(/Could not load the ingredients/);
    expect(screen.queryByText(/\d+ ingredients?$/)).not.toBeInTheDocument();
  });

  it("does not claim a count when a refetch fails but stale data is still cached", async () => {
    // Arrange: the harder half of the case above, and the one a truthiness-only
    // guard passes over. The first load succeeds, so `data` stays populated;
    // the refetch then fails, so isError is true *and* the stale list is still
    // in hand. The table hides itself but the subtitle must not keep asserting
    // a count next to the error.
    let shouldFail = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        shouldFail
          ? Promise.reject(new TypeError("Failed to fetch"))
          : Promise.resolve(jsonResponse(200, [FLOUR])),
      ),
    );
    // Act
    const { queryClient } = renderPage();
    expect(await screen.findByText("1 ingredient")).toBeInTheDocument();
    shouldFail = true;
    await queryClient.invalidateQueries({ queryKey: ["inventory", "ingredients"] });

    // Assert
    expect(await screen.findByText(/Could not load the ingredients/)).toBeInTheDocument();
    expect(screen.queryByText(/\d+ ingredients?$/)).not.toBeInTheDocument();
  });

  it("marks an in-shortage ingredient with the warning icon and error styling, not one at threshold", async () => {
    // Arrange: Basil is below its own threshold (0.500 < 2.000), Flour is not
    // (10.000 >= 1.000) and is deliberately not included in the /alerts
    // response either, exercising the boundary via absence from that list
    // rather than a same-list comparison.
    const BASIL = {
      id: 2,
      name: "Basil",
      unit: "kg",
      current_stock: "0.500",
      min_stock_threshold: "2.000",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/inventory/alerts")) return Promise.resolve(jsonResponse(200, [BASIL]));
        if (String(url).includes("/api/inventory/ingredients"))
          return Promise.resolve(jsonResponse(200, [FLOUR, BASIL]));
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );

    // Act
    renderPage();
    await screen.findByText("Flour");

    // Assert
    const basilRow = screen.getByText("Basil").closest("tr");
    expect(basilRow).not.toBeNull();
    expect(basilRow!.querySelector('[data-testid="WarningAmberIcon"]')).toBeInTheDocument();
    const basilCell = screen.getByText("Basil");
    expect(basilCell).toHaveStyle({ color: "rgb(211, 47, 47)" });
    const flourRow = screen.getByText("Flour").closest("tr");
    expect(flourRow).not.toBeNull();
    expect(flourRow!.querySelector('[data-testid="WarningAmberIcon"]')).not.toBeInTheDocument();
    const flourCell = screen.getByText("Flour");
    expect(flourCell).not.toHaveStyle({ color: "rgb(211, 47, 47)" });
  });

  it("sorts in-shortage rows to the top, alphabetical within each group", async () => {
    // Arrange: raw response order is deliberately not alphabetical anywhere,
    // so a passing test proves the sort, not an accidental pre-sorted fixture.
    const ZUCCHINI = {
      id: 3,
      name: "Zucchini",
      unit: "kg",
      current_stock: "0.100",
      min_stock_threshold: "5.000",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    const APPLE = {
      id: 4,
      name: "Apple",
      unit: "kg",
      current_stock: "0.100",
      min_stock_threshold: "5.000",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    // A second not-in-shortage ingredient, deliberately alphabetically before
    // Flour, so the non-shortage group's own alphabetical ordering is
    // actually exercised rather than assumed from a single-member group.
    const EGGS = {
      id: 5,
      name: "Eggs",
      unit: "piece",
      current_stock: "20.000",
      min_stock_threshold: "5.000",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/inventory/alerts"))
          return Promise.resolve(jsonResponse(200, [ZUCCHINI, APPLE]));
        if (String(url).includes("/api/inventory/ingredients"))
          return Promise.resolve(jsonResponse(200, [FLOUR, ZUCCHINI, EGGS, APPLE]));
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );

    // Act
    renderPage();
    await screen.findByText("Flour");

    // Assert: Apple and Zucchini (both in shortage) come first, alphabetical
    // between themselves, then Eggs and Flour (not in shortage) last, also
    // alphabetical between themselves (Eggs before Flour, not raw-response order).
    const rowNames = screen.getAllByRole("row").slice(1).map((row) => row.textContent);
    const appleIndex = rowNames.findIndex((text) => text?.includes("Apple"));
    const zucchiniIndex = rowNames.findIndex((text) => text?.includes("Zucchini"));
    const eggsIndex = rowNames.findIndex((text) => text?.includes("Eggs"));
    const flourIndex = rowNames.findIndex((text) => text?.includes("Flour"));
    expect(appleIndex).toBeLessThan(zucchiniIndex);
    expect(zucchiniIndex).toBeLessThan(eggsIndex);
    expect(eggsIndex).toBeLessThan(flourIndex);
  });

  it("shows a retry-capable error when only the alerts request fails", async () => {
    // Arrange: /ingredients succeeds, /alerts alone fails — the combined
    // isError must still gate the table, not silently render with no
    // shortage styling applied.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/inventory/alerts")) return Promise.reject(new TypeError("Failed to fetch"));
        if (String(url).includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR]));
        return Promise.reject(new Error(`unexpected request: ${url}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText(/Could not load the ingredients/)).toBeInTheDocument();
    expect(screen.queryByText("Flour")).not.toBeInTheDocument();
  });

  it("retry re-fires both the ingredients and alerts requests", async () => {
    // Arrange
    const fetchMock = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText(/Could not load the ingredients/);
    const callsBeforeRetry = fetchMock.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Retry" }));

    // Assert: both queries' own requests fire again, not just one.
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(callsBeforeRetry + 2));
  });
});
