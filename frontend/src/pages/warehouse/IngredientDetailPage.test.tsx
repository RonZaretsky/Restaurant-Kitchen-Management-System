import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IngredientDetailPage } from "./IngredientDetailPage";

// Mocks only fetch, driving the real inventoryService hooks, matching
// IngredientsPage.test.tsx's established pattern: mocking the service itself
// would hide the invalidate-and-refetch wiring between the mutation and the
// stat cards/movement history.

const INGREDIENT = {
  id: 7,
  name: "Tomato",
  unit: "kg",
  current_stock: "10.000",
  min_stock_threshold: "2.000",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const PURCHASE_MOVEMENT = {
  id: 1,
  ingredient_id: 7,
  movement_type: "purchase",
  quantity_change: "5.000",
  reference_id: null,
  performed_by: 3,
  timestamp: "2026-01-01T10:00:00Z",
  notes: "restock from supplier",
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
 * Answers every read this page makes, so each test only has to describe what it changes.
 * Order matters: the movements URL must be matched before the plainer ingredient URL, since
 * the movements path also contains the ingredient path as a prefix.
 */
function stubReads(overrides: { ingredient?: Response; movements?: unknown } = {}) {
  return (url: string, _init: RequestInit = {}) => {
    const path = String(url);
    if (path.includes("/api/inventory/ingredients/7/movements")) {
      return Promise.resolve(jsonResponse(200, overrides.movements ?? []));
    }
    if (path.includes("/api/inventory/ingredients/7")) {
      return Promise.resolve(overrides.ingredient ?? jsonResponse(200, INGREDIENT));
    }
    return Promise.reject(new Error(`unexpected request: ${path}`));
  };
}

function renderPage(initialPath = "/warehouse/ingredients/7") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/warehouse/ingredients/:ingredientId" element={<IngredientDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("IngredientDetailPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the stat cards from the ingredient GET response", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads()));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByRole("heading", { name: "Tomato" })).toBeInTheDocument();
    expect(screen.getByText("10.000 kg")).toBeInTheDocument();
    expect(screen.getByText("2.000 kg")).toBeInTheDocument();
  });

  it("renders a movement history row with type, signed quantity, note, and timestamp", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads({ movements: [PURCHASE_MOVEMENT] })));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Purchase")).toBeInTheDocument();
    expect(screen.getByText("+5.000 kg")).toBeInTheDocument();
    expect(screen.getByText("restock from supplier")).toBeInTheDocument();
    expect(screen.getByText(new Date(PURCHASE_MOVEMENT.timestamp).toLocaleString())).toBeInTheDocument();
  });

  it("shows the exact empty-state copy when there are no movements yet", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads()));

    // Act
    renderPage();

    // Assert: UX-DR15's exact required copy.
    expect(await screen.findByText("No stock movements yet")).toBeInTheDocument();
  });

  it("offers Purchase/Waste/Adjustment but never Consumption as a movement type", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(stubReads()));
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("combobox", { name: "Movement type" }));

    // Assert
    expect(await screen.findByRole("option", { name: "Purchase" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Waste" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Adjustment" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Consumption" })).not.toBeInTheDocument();
  });

  it("submits a purchase movement with the exact body and clears the form on success", async () => {
    // Arrange: the mock's own state tracks recorded movements, so the GET issued after the
    // POST's cache invalidation reflects the addition.
    let movements: Array<Record<string, unknown>> = [];
    let submitted: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/movements") && init.method === "POST") {
          submitted = JSON.parse(String(init.body));
          const created = { ...PURCHASE_MOVEMENT, id: movements.length + 1, ...submitted };
          movements = [...movements, created];
          return Promise.resolve(jsonResponse(201, created));
        }
        return stubReads({ movements })(url);
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("No stock movements yet");
    await user.click(screen.getByRole("combobox", { name: "Movement type" }));
    await user.click(await screen.findByRole("option", { name: "Purchase" }));
    await user.type(screen.getByLabelText("Quantity (kg)"), "5");
    await user.click(screen.getByRole("button", { name: "Log movement" }));

    // Assert
    await screen.findByText("Purchase");
    expect(submitted).toEqual({ movement_type: "purchase", quantity: "5", notes: null });
    expect(screen.getByLabelText("Quantity (kg)")).toHaveValue("");
    expect(screen.getByRole("combobox", { name: "Movement type" })).not.toHaveTextContent("Purchase");
  });

  it("accepts a leading '-' for an adjustment and sends it as typed", async () => {
    // Arrange
    let submitted: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/movements") && init.method === "POST") {
          submitted = JSON.parse(String(init.body));
          return Promise.resolve(jsonResponse(201, { ...PURCHASE_MOVEMENT, ...submitted }));
        }
        return stubReads()(url);
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("No stock movements yet");
    await user.click(screen.getByRole("combobox", { name: "Movement type" }));
    await user.click(await screen.findByRole("option", { name: "Adjustment" }));
    await user.type(screen.getByLabelText("Quantity (kg)"), "-3.5");
    await user.click(screen.getByRole("button", { name: "Log movement" }));

    // Assert
    await vi.waitFor(() => expect(submitted).toBeDefined());
    expect(submitted).toEqual({ movement_type: "adjustment", quantity: "-3.5", notes: null });
  });

  it("keeps the submit button disabled for an invalid or zero quantity", async () => {
    // Arrange
    const fetchMock = vi.fn(stubReads());
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("No stock movements yet");
    await user.click(screen.getByRole("combobox", { name: "Movement type" }));
    await user.click(await screen.findByRole("option", { name: "Purchase" }));
    await user.type(screen.getByLabelText("Quantity (kg)"), "0");

    // Assert: the reason is visible, and no POST was ever attempted.
    expect(await screen.findByText("Enter a valid, non-zero amount")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log movement" })).toBeDisabled();
    expect(fetchMock.mock.calls.every(([, init]) => (init as RequestInit)?.method !== "POST")).toBe(true);
  });

  it("surfaces a 422 rejection inline and preserves the typed form values", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/movements") && init.method === "POST") {
          return Promise.resolve(
            jsonResponse(422, { detail: "quantity must be greater than zero for a purchase or waste movement" }),
          );
        }
        return stubReads()(url);
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("No stock movements yet");
    await user.click(screen.getByRole("combobox", { name: "Movement type" }));
    await user.click(await screen.findByRole("option", { name: "Purchase" }));
    await user.type(screen.getByLabelText("Quantity (kg)"), "5");
    await user.click(screen.getByRole("button", { name: "Log movement" }));

    // Assert: the backend's literal string, unrewritten, and the typed values stay.
    expect(
      await screen.findByText("quantity must be greater than zero for a purchase or waste movement"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Quantity (kg)")).toHaveValue("5");
  });

  it("shows the same not-found message for an invalid route param, with no movements fetch", async () => {
    // Arrange
    const fetchMock = vi.fn(stubReads());
    vi.stubGlobal("fetch", fetchMock);

    // Act
    renderPage("/warehouse/ingredients/abc");

    // Assert: no fetch attempted at all when the param itself is invalid.
    expect(await screen.findByText(/That ingredient link is not valid/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/movements"))).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the same not-found message for a genuine backend 404", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn(stubReads({ ingredient: jsonResponse(404, { detail: "Ingredient not found" }) })),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText(/That ingredient link is not valid/)).toBeInTheDocument();
  });
});
