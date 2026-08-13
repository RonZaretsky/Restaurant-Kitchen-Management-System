import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DishesPage } from "./DishesPage";

// Mocks only fetch, driving the real menuService/inventoryService hooks, matching
// MenuManagementPage.test.tsx's pattern: mocking the service itself would hide
// real wiring bugs (Story 1.4's established lesson).

const CATEGORY = { id: 1, name: "Pizza" };
const AVAILABLE_DISH = {
  id: 10,
  name: "Margherita",
  description: "Tomato, mozzarella, basil",
  price: "12.50",
  category_id: 1,
  is_available: true,
  prep_time_minutes: 15,
  created_at: "2026-01-01T00:00:00Z",
};
const UNAVAILABLE_DISH = {
  id: 11,
  name: "Carbonara",
  description: null,
  price: "14.00",
  category_id: 1,
  is_available: false,
  prep_time_minutes: 20,
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
const TOMATO = {
  id: 101,
  name: "Tomato",
  unit: "kg",
  current_stock: "5.000",
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
      <DishesPage />
    </QueryClientProvider>,
  );
}

describe("DishesPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders every dish with its fields, category, availability, and recipe by ingredient name", async () => {
    // Arrange
    const line = { dish_id: 10, ingredient_id: FLOUR.id, quantity: "0.300", unit: "kg" };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("/api/menu/dishes/10/recipe-ingredients")) return Promise.resolve(jsonResponse(200, [line]));
        if (path.includes("recipe-ingredients")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [AVAILABLE_DISH]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR, TOMATO]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert: dish fields, not raw ids.
    expect(await screen.findByText("Margherita")).toBeInTheDocument();
    expect(screen.getByText("Pizza")).toBeInTheDocument();
    expect(screen.getByText("Tomato, mozzarella, basil")).toBeInTheDocument();
    expect(screen.getByText(/\$12\.50/)).toBeInTheDocument();
    expect(screen.getByText(/15 min/)).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
    // The recipe line renders the Ingredient's name, never its bare id.
    expect(await screen.findByText("Flour")).toBeInTheDocument();
  });

  it("marks an unavailable dish distinctly", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("recipe-ingredients")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [UNAVAILABLE_DISH]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, []));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Carbonara")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("renders no create, edit, availability-toggle, or delete control anywhere (AC2)", async () => {
    // Arrange
    const line = { dish_id: 10, ingredient_id: FLOUR.id, quantity: "0.300", unit: "kg" };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("/api/menu/dishes/10/recipe-ingredients")) return Promise.resolve(jsonResponse(200, [line]));
        if (path.includes("recipe-ingredients")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [AVAILABLE_DISH]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();
    await screen.findByText("Margherita");

    // Assert: no button, switch, checkbox, textbox, or combobox exists on a
    // strictly read-only surface. Asserting absence of every write affordance
    // shape, not just presence of read-only text.
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    expect(screen.queryAllByRole("combobox")).toHaveLength(0);
  });

  it('shows "No dishes on the menu yet" when the catalog is empty', async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, []));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No dishes on the menu yet")).toBeInTheDocument();
  });

  it("shows an error with a retry when the dish list cannot be loaded", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));

    // Act
    renderPage();

    // Assert: a real error affordance, not a silently blank page.
    expect(await screen.findByText(/Could not load the dish catalog/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("reports a failed recipe fetch as an error, not as an empty recipe", async () => {
    // Arrange: an errored query and a genuinely empty one must not collapse into
    // the same "no recipe" claim.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("recipe-ingredients")) {
          return Promise.resolve(jsonResponse(500, { detail: "Server error" }));
        }
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [AVAILABLE_DISH]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();
    await screen.findByText("Margherita");

    // Assert
    expect(await screen.findByText(/Could not load this recipe/)).toBeInTheDocument();
    expect(screen.queryByText("No recipe ingredients yet.")).not.toBeInTheDocument();
  });

  it("surfaces a categories-fetch failure as an error, not a silent blank page", async () => {
    // Arrange: dishes succeeds, categories fails. Reproduced against the pre-fix
    // code first (only useDishes()'s isError was wired up): the page rendered
    // only the "Dishes" heading with nothing else, no error, no empty-state text.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) {
          return Promise.resolve(jsonResponse(500, { detail: "Server error" }));
        }
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [AVAILABLE_DISH]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText(/Could not load the dish catalog/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText("Margherita")).not.toBeInTheDocument();
  });

  it("still shows a Dish whose Category cannot be resolved, under a fallback heading", async () => {
    // Arrange: the Dish references a category_id with no matching Category (the
    // categories fetch succeeded but returned an empty list, e.g. a stale
    // reference). Reproduced against the pre-fix code first: grouping only
    // iterated the Category list, so a Dish like this was silently dropped.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("recipe-ingredients")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [AVAILABLE_DISH]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, []));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert: the Dish still renders, grouped under a `#{id}` fallback heading.
    expect(await screen.findByText("Margherita")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
  });

  it("warns instead of silently showing raw ingredient ids when the ingredient list fails", async () => {
    // Arrange: recipe line resolves, but the Ingredient list fetch fails.
    // Reproduced against the pre-fix code first: the line rendered as "#100"
    // with no indication anything had gone wrong.
    const line = { dish_id: 10, ingredient_id: FLOUR.id, quantity: "0.300", unit: "kg" };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("/api/menu/dishes/10/recipe-ingredients")) return Promise.resolve(jsonResponse(200, [line]));
        if (path.includes("recipe-ingredients")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [AVAILABLE_DISH]));
        if (path.includes("/api/inventory/ingredients")) {
          return Promise.resolve(jsonResponse(500, { detail: "Server error" }));
        }
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();
    await screen.findByText("Margherita");

    // Assert
    expect(
      await screen.findByText("Could not load ingredient names, showing ingredient ids instead."),
    ).toBeInTheDocument();
  });

  it("hides a Category with zero Dishes rather than showing an empty group", async () => {
    // Arrange: two Categories exist, only one has a Dish.
    const emptyCategory = { id: 2, name: "Desserts" };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/menu/categories")) {
          return Promise.resolve(jsonResponse(200, [CATEGORY, emptyCategory]));
        }
        if (path.includes("recipe-ingredients")) return Promise.resolve(jsonResponse(200, []));
        if (path.includes("/api/menu/dishes")) return Promise.resolve(jsonResponse(200, [AVAILABLE_DISH]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [FLOUR]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Pizza")).toBeInTheDocument();
    expect(screen.queryByText("Desserts")).not.toBeInTheDocument();
  });
});
