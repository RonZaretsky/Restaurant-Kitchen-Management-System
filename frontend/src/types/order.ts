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

/**
 * Mirrors backend/data_models/order.py's OrderItemStatus enum values exactly.
 *
 * Deliberately only 3 members: `cancelled` (AD-11) does not exist on the backend enum until
 * Story 3.4 ships its own migration, do not add it speculatively.
 */
export type OrderItemStatus = "pending" | "in_preparation" | "ready";

/**
 * Mirrors the JSON shape of backend/data_models/order.py's OrderItemResponse.
 *
 * `price_at_add` stays a string, same Decimal-as-string reasoning as `Order.total_amount` above.
 */
export interface OrderItem {
  id: number;
  order_id: number;
  dish_id: number;
  quantity: number;
  status: OrderItemStatus;
  notes: string | null;
  cook_id: number | null;
  price_at_add: string;
}
