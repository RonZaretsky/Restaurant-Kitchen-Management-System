/** Mirrors backend/data_models/order.py's OrderStatus enum values exactly. */
export type OrderStatus = "pending" | "in_preparation" | "ready" | "served" | "closed";

/**
 * Mirrors the JSON shape of backend/data_models/order.py's OrderResponse.
 *
 * `total_amount` stays a string when present, matching Dish.price's
 * Decimal-as-string precedent (Pydantic serializes a Decimal as a JSON
 * string, never a float, so no precision is lost in transit).
 */
export interface Order {
  id: number;
  table_id: number;
  waiter_id: number;
  status: OrderStatus;
  created_at: string;
  closed_at: string | null;
  total_amount: string | null;
}
