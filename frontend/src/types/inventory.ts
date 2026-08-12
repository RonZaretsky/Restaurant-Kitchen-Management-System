import type { Unit } from "./menu";

/**
 * Mirrors the JSON shape of backend/data_models/recipe.py's
 * IngredientResponse. `current_stock`/`min_stock_threshold` stay strings,
 * matching Dish.price's Decimal-as-string precedent.
 */
export interface Ingredient {
  id: number;
  name: string;
  unit: Unit;
  current_stock: string;
  min_stock_threshold: string;
  created_at: string;
  updated_at: string;
}
