/** Mirrors backend/data_models/recipe.py's Unit enum values exactly. */
export type Unit = "kg" | "liter" | "piece";

/** Mirrors the JSON shape of backend/data_models/menu.py's CategoryResponse. */
export interface Category {
  id: number;
  name: string;
}

/**
 * Mirrors the JSON shape of backend/data_models/menu.py's DishResponse.
 *
 * `price` stays a string: Pydantic serializes a Decimal field as a JSON
 * string, never a float, so no precision is lost in transit.
 */
export interface Dish {
  id: number;
  name: string;
  description: string | null;
  price: string;
  category_id: number;
  is_available: boolean;
  prep_time_minutes: number | null;
  created_at: string;
}

/**
 * Mirrors the JSON shape of backend/data_models/recipe.py's
 * RecipeIngredientResponse. No `ingredient_name`, deliberately: the response
 * maps 1:1 to the ORM row, callers join against the Ingredient list
 * (useIngredients) themselves for display.
 */
export interface RecipeIngredient {
  dish_id: number;
  ingredient_id: number;
  quantity: string;
  unit: Unit;
}
