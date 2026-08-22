import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RecipeSuggestionsPage } from "./RecipeSuggestionsPage";

// Mocks only fetch, driving the real smartChefService/menuService/inventoryService hooks,
// matching SmartChefPage.test.tsx's established pattern.

const CATEGORY = { id: 1, name: "Pizza" };
const ZUCCHINI = {
  id: 100,
  name: "Zucchini",
  unit: "kg",
  current_stock: "5.000",
  min_stock_threshold: "1.000",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function suggestion(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1,
    requested_by: 3,
    prompt_used: "...",
    generated_recipe: {
      name: "Roasted Zucchini Flatbread",
      ingredients: [{ name: "Zucchini", quantity: "1.2 kg" }],
      plating: "Sliced thin, served on a wooden board.",
    },
    ingredients_snapshot: [{ name: "Zucchini", unit: "kg", current_stock: "5.000" }],
    created_at: "2026-01-01T18:42:00Z",
    dismissed: false,
    confirmed_dish_id: null,
    ...overrides,
  };
}

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
      <RecipeSuggestionsPage />
    </QueryClientProvider>,
  );
}

describe("RecipeSuggestionsPage", () => {
  it("shows the empty-state copy when nothing is awaiting review", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(200, []))));

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No suggestions awaiting review.")).toBeInTheDocument();
  });

  it("excludes a dismissed or already-confirmed suggestion even though the raw response includes it", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(200, [suggestion({ id: 1, dismissed: true }), suggestion({ id: 2, confirmed_dish_id: 42 })]),
        ),
      ),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("No suggestions awaiting review.")).toBeInTheDocument();
  });

  it("renders a card with Confirm and Dismiss actions for a suggestion awaiting review", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/smart-chef/suggestions")) return Promise.resolve(jsonResponse(200, [suggestion()]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );

    // Act
    renderPage();

    // Assert
    expect(await screen.findByText("Roasted Zucchini Flatbread")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm into Dish" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
  });

  it("calls the dismiss endpoint directly on Dismiss, with no confirm step", async () => {
    // Arrange
    let dismissCalled = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/dismiss")) {
          dismissCalled = true;
          expect(init.method).toBe("POST");
          return Promise.resolve(jsonResponse(200, suggestion({ dismissed: true })));
        }
        return Promise.resolve(jsonResponse(200, [suggestion()]));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("Roasted Zucchini Flatbread");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    // Assert
    await vi.waitFor(() => expect(dismissCalled).toBe(true));
  });

  it("opens the confirm dialog with the suggestion's name/description prefilled and an ingredient row matched to the real Ingredient", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const path = String(url);
        if (path.includes("/api/smart-chef/suggestions")) return Promise.resolve(jsonResponse(200, [suggestion()]));
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [ZUCCHINI]));
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("Roasted Zucchini Flatbread");
    await user.click(screen.getByRole("button", { name: "Confirm into Dish" }));

    // Assert: the dialog opened (title distinguishes it from the button of the same text) with
    // the dish fields prefilled and the ingredient row matched/parsed.
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Confirm into Dish" })).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Dish name")).toHaveValue("Roasted Zucchini Flatbread");
    expect(within(dialog).getByLabelText("Description")).toHaveValue("Sliced thin, served on a wooden board.");
    await vi.waitFor(() => expect(within(dialog).getByDisplayValue("1.2")).toBeInTheDocument());
  });

  it("creates the Dish and its Recipe Ingredient line together on Confirm", async () => {
    // Arrange
    let dishPostBody: Record<string, unknown> | undefined;
    let recipeIngredientPostBody: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        const path = String(url);
        if (path.includes("/api/smart-chef/suggestions")) return Promise.resolve(jsonResponse(200, [suggestion()]));
        if (path.includes("/api/menu/categories")) return Promise.resolve(jsonResponse(200, [CATEGORY]));
        if (path.includes("/api/inventory/ingredients")) return Promise.resolve(jsonResponse(200, [ZUCCHINI]));
        if (path.includes("/recipe-ingredients") && init.method === "POST") {
          const body = JSON.parse(String(init.body)) as Record<string, unknown>;
          recipeIngredientPostBody = body;
          return Promise.resolve(
            jsonResponse(201, { dish_id: 55, ingredient_id: body.ingredient_id, quantity: "1.200", unit: "kg" }),
          );
        }
        if (path.includes("/api/menu/dishes") && init.method === "POST") {
          const body = JSON.parse(String(init.body)) as Record<string, unknown>;
          dishPostBody = body;
          return Promise.resolve(
            jsonResponse(201, {
              id: 55,
              name: body.name,
              description: body.description ?? null,
              price: body.price,
              category_id: body.category_id,
              is_available: false,
              prep_time_minutes: null,
              created_at: "2026-01-01T00:00:00Z",
              source_suggestion_id: body.source_suggestion_id,
            }),
          );
        }
        return Promise.reject(new Error(`unexpected request: ${path}`));
      }),
    );
    const user = userEvent.setup();

    // Act
    renderPage();
    await screen.findByText("Roasted Zucchini Flatbread");
    await user.click(screen.getByRole("button", { name: "Confirm into Dish" }));
    const dialog = await screen.findByRole("dialog");
    await vi.waitFor(() => expect(within(dialog).getByDisplayValue("1.2")).toBeInTheDocument());
    await user.type(within(dialog).getByLabelText("Price"), "12.50");
    await user.click(within(dialog).getByRole("combobox", { name: "Category" }));
    await user.click(await screen.findByRole("option", { name: "Pizza" }));
    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));

    // Assert: the Dish carries source_suggestion_id, and the matched ingredient's own real id
    // and unit reached the recipe-ingredient POST, not the AI's free-text name/unit.
    await vi.waitFor(() => expect(dishPostBody).toBeDefined());
    expect(dishPostBody!.source_suggestion_id).toBe(1);
    await vi.waitFor(() => expect(recipeIngredientPostBody).toBeDefined());
    expect(recipeIngredientPostBody).toEqual({ ingredient_id: 100, quantity: "1.2", unit: "kg" });
  });
});
