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
 * `cancelled` (AD-11) added by Story 3.4's own migration.
 */
export type OrderItemStatus = "pending" | "in_preparation" | "ready" | "cancelled";

/**
 * Mirrors backend/data_models/order.py's MAX_ORDER_ITEM_QUANTITY.
 *
 * Kept in sync by hand, the same way the status unions above mirror their
 * backend enums. Submitting more than this is a 422, so the form rejects it
 * first rather than letting the server be the only thing that says no.
 */
export const MAX_ORDER_ITEM_QUANTITY = 99;

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
