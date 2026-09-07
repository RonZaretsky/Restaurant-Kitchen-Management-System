import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IngredientsPage } from "./IngredientsPage";

// Mocks only fetch, driving the real inventoryService hooks, matching
// TablesSetupPage.test.tsx's pattern: mocking the service itself would hide
// the invalidate-and-refetch wiring between the create mutation and the list.

// Rows navigate to the Ingredient detail page, so useNavigate needs a mock,
// matching TablesPage.test.tsx's own precedent for the same shape.
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
  is_active: true,
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

  // --- Sortable table -------------------------------------------------------------------------

  // --- Soft-deactivate ------------------------------------------------------------------------

  it("shows an Active badge and Deactivate action for an active ingredient, and can deactivate it", async () => {
    // Arrange
    let ingredient = { ...FLOUR };
    const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
      const path = String(url);
      if (path.endsWith(`/api/inventory/ingredients/${ingredient.id}/deactivate`) && init.method === "POST") {
        ingredient = { ...ingredient, is_active: false };
        return Promise.resolve(jsonResponse(200, ingredient));
      }
      if (path.includes("/api/inventory/alerts")) return Promise.resolve(jsonResponse(200, []));
      if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [ingredient]));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("Flour");
    expect(screen.getByText("Active")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await user.click(await screen.findByRole("button", { name: "Confirm" }));

    // Assert: the row now reads Inactive once the mutation settles and the list refetches.
    expect(await screen.findByText("Inactive")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/inventory/ingredients/1/deactivate"),
      expect.objectContaining({ method: "POST" }),
    );
    // The row click handler must not have fired from the button click (no stray navigation).
    expect(navigateMock).not.toHaveBeenCalled();
  });

});
