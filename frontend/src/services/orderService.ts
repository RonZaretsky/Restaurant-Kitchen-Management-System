import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import type { Order } from "../types/order";
import { apiRequest } from "./httpClient";
import { TABLES_QUERY_KEY } from "./tableService";

/**
 * Opens an available Table into a new Order (AC1).
 *
 * Invalidates the shared Table list on settle, not only on success, the same
 * key `tableService.ts`'s `useTables()` reads, matching `useUpdateTable()`'s
 * own precedent: a lost race (409) means this client's cached `available`
 * status is already stale, and without a refetch the tile keeps rendering as
 * an open target next to the error.
 *
 * @returns The TanStack Query mutation for opening a Table.
 */
export function useOpenTable(): UseMutationResult<Order, Error, number> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (tableId: number) =>
      apiRequest<Order>(`/api/orders/tables/${tableId}/open`, {
        method: "POST",
      }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TABLES_QUERY_KEY }),
  });
}
