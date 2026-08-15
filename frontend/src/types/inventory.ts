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

export type MovementType = "purchase" | "consumption" | "waste" | "adjustment";

/**
 * Mirrors backend/data_models/inventory.py's StockMovementResponse.
 * `quantity_change` stays a string (Decimal-as-string, matching
 * Ingredient.current_stock's own precedent), already signed by the backend
 * (e.g. "-0.800" for a waste movement).
 */
export interface StockMovement {
  id: number;
  ingredient_id: number;
  movement_type: MovementType;
  quantity_change: string;
  reference_id: number | null;
  performed_by: number;
  timestamp: string;
  notes: string | null;
}
