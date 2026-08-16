import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import type { KitchenItem } from "../types/kitchen";
import { apiRequest } from "./httpClient";

/**
 * The shared cache key for the Kitchen Display's live board.
 *
 * Exported (Story 5.1) so KitchenDisplayPage.tsx's own live `order.item_added`
 * subscriber can invalidate the same key this hook uses, matching
 * ALERTS_QUERY_KEY/orderItemsQueryKey's established cross-file-export shape.
 */
export const KITCHEN_ITEMS_QUERY_KEY = ["kitchen", "items"] as const;

/**
 * Fetches every non-cancelled Order Item currently active (Story 5.1).
 *
 * @returns The TanStack Query result for the Kitchen Display's live board.
 */
export function useKitchenItems(): UseQueryResult<KitchenItem[], Error> {
  return useQuery({
    queryKey: KITCHEN_ITEMS_QUERY_KEY,
    queryFn: () => apiRequest<KitchenItem[]>("/api/kitchen/items"),
    retry: false,
  });
}
