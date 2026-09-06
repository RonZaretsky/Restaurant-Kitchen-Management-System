import type { OrderItemStatus } from "./order";

/**
 * Mirrors the JSON shape of backend/data_models/order.py's KitchenItemResponse.
 * OrderItem's exact field set plus table_id, resolved server-side
 * via a join since OrderItem itself has no table_id, only order_id.
 */
export interface KitchenItem {
  id: number;
  order_id: number;
  table_id: number;
  dish_id: number;
  quantity: number;
  status: OrderItemStatus;
  notes: string | null;
  cook_id: number | null;
  price_at_add: string;
  reject_reason: string | null;
  /** How many portions of this item's Dish current stock supports right now. Only meaningful
   * while status is "pending" — the Kitchen Display disables "Pick up" and shows "Reject"
   * instead once this falls below `quantity`. */
  max_preparable_quantity: number;
}
