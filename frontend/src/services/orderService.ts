import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import type { Order, OrderItem } from "../types/order";
import { apiRequest } from "./httpClient";
import { KITCHEN_ITEMS_QUERY_KEY } from "./kitchenService";
import { DISHES_QUERY_KEY } from "./menuService";
import { TABLES_QUERY_KEY } from "./tableService";

interface AddOrderItemPayload {
  dish_id: number;
  quantity: number;
  notes?: string | null;
}

interface EditOrderItemPayload {
  quantity: number;
  notes?: string | null;
}

/**
 * The shared cache key for one Order's item list.
 *
 * Exported (Story 3.3) so TableOrderDetailPage.tsx's live `order.item_added`
 * subscriber can invalidate the same key this file's own query and mutation
 * already use, rather than reconstructing the array by hand and risking the
 * two drifting apart.
 */
export function orderItemsQueryKey(orderId: number | undefined) {
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
 * The shared cache key for one Table's currently open Order.
 *
 * Exported (Story 5.3) so TableOrderDetailPage.tsx's live `order.status_changed` subscriber can
 * invalidate the same key `useOrderForTable` uses, matching `orderItemsQueryKey`'s established
 * cross-file-export shape rather than reconstructing the array by hand.
 *
 * @param tableId - The Table whose open Order key is being built, or null if not yet known.
 */
export function orderForTableQueryKey(tableId: number | null) {
  return ["orders", "table", tableId] as const;
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
    queryKey: orderForTableQueryKey(tableId),
    queryFn: () => apiRequest<Order>(`/api/orders/tables/${tableId}`),
    enabled: tableId !== null,
    retry: false,
  });
}

/**
 * The shared cache key for the bulk open-Orders list (Story 5.3).
 *
 * Exported so TablesPage.tsx's live `order.status_changed` subscriber can invalidate the same
 * key this hook uses, matching `KITCHEN_ITEMS_QUERY_KEY`'s established exported-cache-key shape.
 */
export const OPEN_ORDERS_QUERY_KEY = ["orders", "open"] as const;

/**
 * Fetches every currently open (non-closed) Order, across every Table (Story 5.3, AC4).
 *
 * Backs the Tables grid's need to know, across every occupied Table at once, whether that
 * Table's Order is `ready`, to render the attention-state tile treatment — one bulk query
 * resolved client-side into a table_id -> status lookup, not a per-tile request. `enabled`
 * defaults to true (TablesPage.tsx's own unconditional call site, unchanged); AppShell.tsx
 * (Story 5.4) passes `isWaiter` explicitly, mirroring `useAlerts`'s own Role-gating shape — the
 * backing route is Waiter-only, so an ungated call from a non-Waiter role would 403.
 *
 * @param enabled - Whether the query should run at all.
 * @returns The TanStack Query result for every open Order.
 */
export function useOpenOrders(enabled = true): UseQueryResult<Order[], Error> {
  return useQuery({
    queryKey: OPEN_ORDERS_QUERY_KEY,
    queryFn: () => apiRequest<Order[]>("/api/orders"),
    enabled,
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

/**
 * Edits a pending Order Item's quantity and/or note (AC1).
 *
 * Invalidates on settle, not only on success, matching `useAddOrderItem`'s own reasoning: a 409
 * (the item is no longer pending) means this client's cached row is already stale, and the
 * failing path needs the refetch too.
 *
 * @param orderId - The Order the item belongs to, or undefined before it is known.
 * @returns The TanStack Query mutation for editing an Order Item.
 */
export function useEditOrderItem(
  orderId: number | undefined,
): UseMutationResult<OrderItem, Error, { itemId: number; payload: EditOrderItemPayload }> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: number; payload: EditOrderItemPayload }) =>
      apiRequest<OrderItem>(`/api/orders/${orderId}/items/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: orderItemsQueryKey(orderId) }),
  });
}

/**
 * Cancels a pending or in_preparation Order Item (AC2/AC3).
 *
 * Invalidates on settle for the same reason `useEditOrderItem` does.
 *
 * @param orderId - The Order the item belongs to, or undefined before it is known.
 * @returns The TanStack Query mutation for cancelling an Order Item.
 */
export function useCancelOrderItem(
  orderId: number | undefined,
): UseMutationResult<OrderItem, Error, number> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itemId: number) =>
      apiRequest<OrderItem>(`/api/orders/${orderId}/items/${itemId}/cancel`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: orderItemsQueryKey(orderId) }),
  });
}

interface PickUpOrMarkReadyVariables {
  orderId: number;
  itemId: number;
}

/**
 * Picks up a pending Order Item, triggering atomic stock deduction server-side (Story 5.2, AC1).
 *
 * Unlike `useEditOrderItem`/`useCancelOrderItem`, this hook is not bound to one fixed `orderId`
 * at call time — its only caller, the Kitchen Display, renders items from many different Orders
 * on the same screen (one card per Table), so `orderId` travels with each mutation call instead.
 * Invalidates only `KITCHEN_ITEMS_QUERY_KEY` on settle, not `orderItemsQueryKey`: the Waiter's own
 * Table Order Detail page for this Order refreshes from the live `order.item_status_changed`
 * push instead (matching this codebase's "the live event is what refreshes other pages, not the
 * mutating page's own success handler" precedent), not from this mutation reaching into a cache
 * key it does not otherwise know or care about.
 *
 * @returns The TanStack Query mutation for picking up an Order Item.
 */
export function usePickUpItem(): UseMutationResult<OrderItem, Error, PickUpOrMarkReadyVariables> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ orderId, itemId }: PickUpOrMarkReadyVariables) =>
      apiRequest<OrderItem>(`/api/orders/${orderId}/items/${itemId}/pick-up`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: KITCHEN_ITEMS_QUERY_KEY }),
  });
}

/**
 * Marks an in_preparation Order Item ready, a pure status change (Story 5.2, AC3).
 *
 * Same shape and invalidation reasoning as `usePickUpItem`.
 *
 * @returns The TanStack Query mutation for marking an Order Item ready.
 */
export function useMarkItemReady(): UseMutationResult<OrderItem, Error, PickUpOrMarkReadyVariables> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ orderId, itemId }: PickUpOrMarkReadyVariables) =>
      apiRequest<OrderItem>(`/api/orders/${orderId}/items/${itemId}/mark-ready`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: KITCHEN_ITEMS_QUERY_KEY }),
  });
}

/**
 * Rejects a pending Order Item the kitchen cannot currently prepare (this batch).
 *
 * Same shape and invalidation reasoning as `usePickUpItem`/`useMarkItemReady` — the Waiter's own
 * Table Order Detail page refreshes from the live `order.item_status_changed` push instead, which
 * carries the item's new `reject_reason` for that page to display.
 *
 * @returns The TanStack Query mutation for rejecting an Order Item.
 */
export function useRejectItem(): UseMutationResult<OrderItem, Error, PickUpOrMarkReadyVariables> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ orderId, itemId }: PickUpOrMarkReadyVariables) =>
      apiRequest<OrderItem>(`/api/orders/${orderId}/items/${itemId}/reject`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: KITCHEN_ITEMS_QUERY_KEY }),
  });
}

/**
 * Marks a ready (or zero-item) Order served, a pure status change (Story 5.4, AC1, AC2).
 *
 * Invalidates `orderForTableQueryKey(tableId)` on settle — it is the Order object itself that
 * changes here, not its item list, mirroring `useOrderForTable`'s own tableId-keyed cache
 * precedent rather than introducing a second orderId-keyed variant of the same data.
 *
 * @param orderId - The Order to mark served, or undefined before it is known.
 * @param tableId - The Table this Order belongs to, or null if not yet known.
 * @returns The TanStack Query mutation for marking an Order served.
 */
export function useMarkOrderServed(
  orderId: number | undefined,
  tableId: number | null,
): UseMutationResult<Order, Error, void> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => apiRequest<Order>(`/api/orders/${orderId}/serve`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: orderForTableQueryKey(tableId) }),
  });
}

/**
 * Closes a served Order, computing its total and freeing its Table (Story 5.4, AC3, AC4, AC5).
 *
 * Invalidates only the Table list on settle, deliberately not this Order's own key: a successful
 * close means there is no longer anything open on this Table, and the caller navigates away from
 * this Order's page immediately on success (manual test finding — invalidating
 * `orderForTableQueryKey` here raced the navigation, letting the "no open order" banner flash
 * before the route change committed). `TABLES_QUERY_KEY` still needs invalidating: the Table's
 * own status changed, and the grid the caller navigates to depends on it, the same
 * "invalidate every affected key" rule `useOpenTable` already follows.
 *
 * @param orderId - The Order to close, or undefined before it is known.
 * @returns The TanStack Query mutation for closing an Order.
 */
export function useCloseOrder(orderId: number | undefined): UseMutationResult<Order, Error, void> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => apiRequest<Order>(`/api/orders/${orderId}/close`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TABLES_QUERY_KEY }),
  });
}
