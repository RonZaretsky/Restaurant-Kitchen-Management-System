import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import type { Order, OrderItem } from "../types/order";
import { apiRequest } from "./httpClient";
import { DISHES_QUERY_KEY } from "./menuService";
import { TABLES_QUERY_KEY } from "./tableService";

interface AddOrderItemPayload {
  dish_id: number;
  quantity: number;
  notes?: string | null;
}

/** The shared cache key for one Order's item list, used by the query and its mutation's invalidation. */
function orderItemsQueryKey(orderId: number | undefined) {
  return ["orders", orderId, "items"] as const;
}

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

/**
 * Fetches the Order currently open on a Table.
 *
 * The Table/Order detail page is reached by table_id alone (`/waiter/tables/:tableId`), so this
 * is the read that resolves table_id -> the Order to render, whether reached by direct navigation,
 * a page refresh, or a second Waiter opening the same page.
 *
 * `enabled: tableId !== null` keeps a malformed route param (`/waiter/tables/abc`)
 * from being sent to the server as a request that can only ever 422.
 *
 * @param tableId - The Table whose open Order is being fetched, or null if the
 *   route param was not a usable id.
 * @returns The TanStack Query result for that Table's open Order.
 */
export function useOrderForTable(tableId: number | null): UseQueryResult<Order, Error> {
  return useQuery({
    queryKey: ["orders", "table", tableId] as const,
    queryFn: () => apiRequest<Order>(`/api/orders/tables/${tableId}`),
    enabled: tableId !== null,
    retry: false,
  });
}

/**
 * Fetches every Order Item on an Order (AC3).
 *
 * `enabled: orderId !== undefined`: the page cannot know an Order's id until useOrderForTable
 * resolves, this hook is called before that read settles.
 *
 * @param orderId - The Order whose items are being listed, or undefined before it is known.
 * @returns The TanStack Query result for that Order's item list.
 */
export function useOrderItems(orderId: number | undefined): UseQueryResult<OrderItem[], Error> {
  return useQuery({
    queryKey: orderItemsQueryKey(orderId),
    queryFn: () => apiRequest<OrderItem[]>(`/api/orders/${orderId}/items`),
    enabled: orderId !== undefined,
    retry: false,
  });
}

/**
 * Adds a new Order Item to an Order (AC1).
 *
 * `orderId` is optional because this hook is called before `useOrderForTable` resolves, the same
 * reason `useOrderItems` accepts it optionally. The caller only invokes the returned mutation once
 * an Order is known, submission is gated on that in the page.
 *
 * Invalidates the Dish list on settle as well as the item list. A rejected add is the case that
 * most needs it: a 409 "dish unavailable" means this client's cached copy of that Dish is already
 * stale, and without a refetch the picker keeps offering it, so every retry fails identically.
 * Same reasoning `useUpdateTable`/`useOpenTable` documented for the Table list.
 *
 * @param orderId - The Order the item is being added to, or undefined before it is known.
 * @returns The TanStack Query mutation for submitting a new Order Item.
 */
export function useAddOrderItem(
  orderId: number | undefined,
): UseMutationResult<OrderItem, Error, AddOrderItemPayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AddOrderItemPayload) =>
      apiRequest<OrderItem>(`/api/orders/${orderId}/items`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: orderItemsQueryKey(orderId) });
      await queryClient.invalidateQueries({ queryKey: DISHES_QUERY_KEY });
    },
  });
}
