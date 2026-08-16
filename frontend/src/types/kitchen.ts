import type { OrderItemStatus } from "./order";

/**
 * Mirrors the JSON shape of backend/data_models/order.py's KitchenItemResponse
 * (Story 5.1). OrderItem's exact field set plus table_id, resolved server-side
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
}
