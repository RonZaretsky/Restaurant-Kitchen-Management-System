import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MenuManagementPage } from "./MenuManagementPage";

// Mocks only fetch, driving the real menuService/inventoryService hooks, matching
// appIntegration.test.tsx's pattern: mocking the service itself would hide the
// invalidate-and-refetch wiring this page depends on, where adding a line must
// flip the availability toggle without a page reload.

const CATEGORY = { id: 1, name: "Pizza" };
const DISH = {
  id: 10,
  name: "Margherita",
  description: null,
  price: "12.50",
  category_id: 1,
  is_available: false,
  prep_time_minutes: 15,
  created_at: "2026-01-01T00:00:00Z",
};
const FLOUR = {
  id: 100,
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
  return render(
    <QueryClientProvider client={queryClient}>
      <MenuManagementPage />
    </QueryClientProvider>,
  );
}

describe("MenuManagementPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the dish list from the backend", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [DISH]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Margherita")).toBeInTheDocument();
    expect(screen.getByText("Pizza")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("adding a dish's first recipe ingredient re-enables its availability toggle with no page reload", async () => {
    // Arrange: the mock's own state tracks the recipe, so the GET issued after
    // the POST's cache invalidation reflects the addition, exactly like a real
    // backend would. Reintroducing the bug (never invalidating the
    // recipe-ingredients query on add) makes the final assertion fail, confirmed
    // before trusting it.
    let lines: Array<{ dish_id: number; ingredient_id: number; quantity: string; unit: string }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("recipe-ingredients") && init.method === "POST") {
          const body = JSON.parse(String(init.body));
          const line = { dish_id: DISH.id, ingredient_id: body.ingredient_id, quantity: body.quantity, unit: body.unit };
          lines = [...lines, line];
          return Promise.resolve(jsonResponse(201, line));
        }
        if (path.includes("recipe-ingredients")) return Promise.resolve(jsonResponse(200, lines));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [DISH]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("button", { name: /Expand Margherita/ }));
    expect(await screen.findByRole("switch", { name: /Unavailable/ })).toBeDisabled();

    await user.click(screen.getByRole("combobox", { name: "Ingredient" }));
    await user.click(await screen.findByRole("option", { name: "Flour" }));
    await user.type(screen.getByLabelText("Quantity"), "0.3");
    await user.click(screen.getByRole("button", { name: "+ Add recipe ingredient" }));

    // Assert: waitFor, not a bare findByRole, so this polls the condition under
    // test rather than resolving as soon as any switch exists.
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: /Unavailable/ })).not.toBeDisabled(),
    );
  });

  it("surfaces the backend's exact 409 message when removing an available dish's last line", async () => {
    // Arrange
    const availableDish = { ...DISH, id: 11, is_available: true };
    const line = { dish_id: 11, ingredient_id: FLOUR.id, quantity: "0.300", unit: "kg" };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("recipe-ingredients") && init.method === "DELETE") {
          return Promise.resolve(
            jsonResponse(409, { detail: "Cannot remove the last recipe ingredient while the dish is available" }),
          );
        }
        if (path.includes("recipe-ingredients")) return Promise.resolve(jsonResponse(200, [line]));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [availableDish]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click(await screen.findByRole("button", { name: /Expand Margherita/ }));
    await user.click(await screen.findByRole("button", { name: /Remove Flour/ }));

    // Assert
    expect(
      await screen.findByText("Cannot remove the last recipe ingredient while the dish is available"),
    ).toBeInTheDocument();
  });

  it("creates a dish and clears the form", async () => {
    // Arrange: the mock's own state tracks created dishes, so the GET issued
    // after the POST's cache invalidation reflects the addition.
    let dishes: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
      const path = String(url);
      if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
      if (path.includes("/api/menu/dishes") && init.method === "POST") {
        const body = JSON.parse(String(init.body));
        const created = {
          id: 99,
          name: body.name,
          description: body.description ?? null,
          price: body.price,
          category_id: body.category_id,
          is_available: false,
          prep_time_minutes: body.prep_time_minutes ?? null,
          created_at: "2026-01-01T00:00:00Z",
        };
        dishes = [...dishes, created];
        return Promise.resolve(jsonResponse(201, created));
      }
      if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, dishes));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("No dishes yet.");
    await user.type(screen.getByLabelText("Dish name"), "Calzone");
    await user.type(screen.getByLabelText("Price"), "9.50");
    await user.click(screen.getByRole("combobox", { name: "Category" }));
    await user.click(await screen.findByRole("option", { name: "Pizza" }));
    await user.click(screen.getByRole("button", { name: "+ New dish" }));

    // Assert: the dish appears, the form clears, and the exact payload sent
    // omits the fields left blank rather than sending null/NaN for them.
    expect(await screen.findByText("Calzone")).toBeInTheDocument();
    // Every field the success handler clears, not just the first one: any of
    // them silently ceasing to reset would otherwise go unnoticed.
    expect(screen.getByLabelText("Dish name")).toHaveValue("");
    expect(screen.getByLabelText("Description")).toHaveValue("");
    expect(screen.getByLabelText("Price")).toHaveValue("");
    expect(screen.getByLabelText("Prep time (minutes)")).toHaveValue("");
    // MUI renders a zero-width-space placeholder in an empty select, so assert
    // the previously chosen label is gone rather than that the node is empty.
    expect(screen.getByRole("combobox", { name: "Category" })).not.toHaveTextContent("Pizza");
    const post = fetchMock.mock.calls.find(
      ([reqUrl, reqInit]) =>
        String(reqUrl).includes("/api/menu/dishes") && (reqInit as RequestInit)?.method === "POST",
    );
    expect(post).toBeDefined();
    expect(JSON.parse(String((post![1] as RequestInit).body))).toEqual({
      name: "Calzone",
      price: "9.50",
      category_id: 1,
    });
  });

  it("surfaces a rejected dish submission inline with the backend's exact message", async () => {
    // Arrange: the category-rejection half was covered but the dish half was
    // not, leaving createDishMutation's own Alert branch unverified.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("/api/menu/dishes") && init.method === "POST") {
          return Promise.resolve(jsonResponse(404, { detail: "Category not found" }));
        }
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, []));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("No dishes yet.");
    await user.type(screen.getByLabelText("Dish name"), "Orphan");
    await user.type(screen.getByLabelText("Price"), "5.00");
    await user.click(screen.getByRole("combobox", { name: "Category" }));
    await user.click(await screen.findByRole("option", { name: "Pizza" }));
    await user.click(screen.getByRole("button", { name: "+ New dish" }));

    // Assert: the backend's literal string, unrewritten, and the typed values
    // are preserved so the Admin can correct and resubmit.
    expect(await screen.findByText("Category not found")).toBeInTheDocument();
    expect(screen.getByLabelText("Dish name")).toHaveValue("Orphan");
  });

});
