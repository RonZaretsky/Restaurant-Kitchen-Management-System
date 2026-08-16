import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useQueryClient } from "@tanstack/react-query";

import { OrderItemStatusBadge } from "../../components/orders/OrderItemStatusBadge";
import { useRealtime } from "../../components/shell/RealtimeProvider";
import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { KITCHEN_ITEMS_QUERY_KEY, useKitchenItems } from "../../services/kitchenService";
import { DISHES_QUERY_KEY, useDishes } from "../../services/menuService";
import { usePickUpItem, useMarkItemReady } from "../../services/orderService";
import { TABLES_QUERY_KEY, useTables } from "../../services/tableService";
import type { KitchenItem } from "../../types/kitchen";

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

/**
 * Reads the human-readable message off a failed request.
 *
 * @param error - The error a query failed with.
 * @returns The message to display inline.
 */
function errorMessage(error: Error): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return GENERIC_ERROR_MESSAGE;
}

/**
 * The Kitchen Display surface (Story 5.1, replacing Epic 1's placeholder).
 *
 * Read-only: one card per Table, grouping that Table's active (non-cancelled) Order Items, each
 * row showing its dish name, quantity, note, and OrderItemStatusBadge (UX-DR1). No pick-up/
 * mark-ready controls anywhere — those are Story 5.2. Dark-theme initialization (UX-DR7) and the
 * "Reconnecting..." banner (UX-DR16) are both already handled globally
 * (ThemeModeProvider/ReconnectingBanner, Stories 1.4/1.5) and need no page-level code here.
 *
 * Subscribes to the live `order.item_added` push (Story 3.3's event, widened in this story to
 * also reach Cook connections) and invalidates KITCHEN_ITEMS_QUERY_KEY, TABLES_QUERY_KEY, and
 * DISHES_QUERY_KEY on receipt (review finding, Story 5.1): the new item's table_id/dish_id could
 * reference a Table or Dish created after this page's own tables/dishes queries last resolved,
 * and this page never otherwise refetches those two long-lived queries on its own (no window-
 * focus refetch is guaranteed on a screen meant to stay foregrounded for a whole shift). Harmless
 * over-invalidation the rest of the time, matching this codebase's established "invalidate is a
 * no-op if nothing changed" doctrine (e.g. useAddOrderItem invalidating DISHES_QUERY_KEY on every
 * settle, not just a 409).
 *
 * Combines loading/error across all three queries this page depends on (kitchen items, tables,
 * dishes) — the established "a page driven by more than one independent query must combine
 * loading/error across all of them" rule, applied here for the first time across three queries.
 *
 * Story 5.2 adds the pick-up/mark-ready action buttons this story's own Scope note explicitly
 * deferred: each `pending` row gets a "Pick up" button, each `in_preparation` row gets a "Mark
 * ready" button (UX-DR19, a single large click target), and `ready` rows get none. Subscribes to
 * the new `order.item_status_changed` push and invalidates KITCHEN_ITEMS_QUERY_KEY on receipt,
 * alongside the existing `order.item_added` subscription. A failed pick-up/mark-ready call shows
 * an inline error under that row (UX-DR17), not a toast — this codebase has no toast/snackbar
 * system anywhere else, so this story does not introduce one either.
 *
 * @returns The Kitchen Display page.
 */
export function KitchenDisplayPage() {
  const queryClient = useQueryClient();
  const { subscribe } = useRealtime();
  const {
    data: items,
    isLoading: isItemsLoading,
    isError: isItemsError,
    error: itemsError,
    refetch: refetchItems,
  } = useKitchenItems();
  const {
    data: tables,
    isLoading: isTablesLoading,
    isError: isTablesError,
    error: tablesError,
    refetch: refetchTables,
  } = useTables();
  const {
    data: dishes,
    isLoading: isDishesLoading,
    isError: isDishesError,
    error: dishesError,
    refetch: refetchDishes,
  } = useDishes();
  const pickUpMutation = usePickUpItem();
  const markReadyMutation = useMarkItemReady();
  const [actionErrors, setActionErrors] = useState<Record<number, string>>({});
  // Tracked as an explicit Set rather than derived from pickUpMutation.variables/markReadyMutation.variables
  // (review finding, Story 5.2): a single shared mutation's .variables only ever reflects the most
  // recent call, so two rapid clicks on different rows before React re-renders could leave an
  // earlier row's button incorrectly re-enabled while its request is still in flight. Adding to
  // the Set synchronously before mutate() and removing it in onSettled closes that window.
  const [pendingPickUpIds, setPendingPickUpIds] = useState<Set<number>>(new Set());
  const [pendingMarkReadyIds, setPendingMarkReadyIds] = useState<Set<number>>(new Set());

  const isLoading = isItemsLoading || isTablesLoading || isDishesLoading;
  const isError = isItemsError || isTablesError || isDishesError;
  const loadError = itemsError ?? tablesError ?? dishesError;
  const refetch = () => {
    void refetchItems();
    void refetchTables();
    void refetchDishes();
  };

  useEffect(() => {
    const unsubscribeItemAdded = subscribe("order.item_added", () => {
      void queryClient.invalidateQueries({ queryKey: KITCHEN_ITEMS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: TABLES_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: DISHES_QUERY_KEY });
    });
    const unsubscribeItemStatusChanged = subscribe("order.item_status_changed", (payload) => {
      void queryClient.invalidateQueries({ queryKey: KITCHEN_ITEMS_QUERY_KEY });
      // Clears a stale inline error for this item (review finding, Story 5.2): a prior
      // pick-up/mark-ready call from this or another session may have failed and left an error
      // showing under this row, but a live status-change event proves the item has since moved
      // on correctly, so that error no longer describes the row's current state.
      const changedItemId = (payload as { id?: unknown } | null)?.id;
      if (typeof changedItemId === "number") {
        setActionErrors((previous) => {
          if (!(changedItemId in previous)) {
            return previous;
          }
          const next = { ...previous };
          delete next[changedItemId];
          return next;
        });
      }
    });
    return () => {
      unsubscribeItemAdded();
      unsubscribeItemStatusChanged();
    };
  }, [subscribe, queryClient]);

  const clearActionError = (itemId: number) => {
    setActionErrors((previous) => {
      if (!(itemId in previous)) {
        return previous;
      }
      const next = { ...previous };
      delete next[itemId];
      return next;
    });
  };

  const handlePickUp = (item: KitchenItem) => {
    if (pendingPickUpIds.has(item.id)) {
      return;
    }
    clearActionError(item.id);
    setPendingPickUpIds((previous) => new Set(previous).add(item.id));
    pickUpMutation.mutate(
      { orderId: item.order_id, itemId: item.id },
      {
        onError: (error) =>
          setActionErrors((previous) => ({ ...previous, [item.id]: errorMessage(error) })),
        onSettled: () =>
          setPendingPickUpIds((previous) => {
            const next = new Set(previous);
            next.delete(item.id);
            return next;
          }),
      },
    );
  };

  const handleMarkReady = (item: KitchenItem) => {
    if (pendingMarkReadyIds.has(item.id)) {
      return;
    }
    clearActionError(item.id);
    setPendingMarkReadyIds((previous) => new Set(previous).add(item.id));
    markReadyMutation.mutate(
      { orderId: item.order_id, itemId: item.id },
      {
        onError: (error) =>
          setActionErrors((previous) => ({ ...previous, [item.id]: errorMessage(error) })),
        onSettled: () =>
          setPendingMarkReadyIds((previous) => {
            const next = new Set(previous);
            next.delete(item.id);
            return next;
          }),
      },
    );
  };

  // Falls back to a bare, clearly-unresolved label rather than the raw internal id (never show a
  // raw id, matching TableOrderDetailPage.tsx's own precedent) — a real table_number could
  // plausibly equal a stale table_id by coincidence, which would be indistinguishable from a
  // genuine table if the fallback echoed the id itself.
  const tableNumber = (tableId: number) => tables?.find((table) => table.id === tableId)?.table_number ?? "?";
  const dishName = (dishId: number) => dishes?.find((dish) => dish.id === dishId)?.name ?? "Unknown dish";

  const itemsByTable = useMemo(() => {
    const grouped = new Map<number, KitchenItem[]>();
    for (const item of items ?? []) {
      const existing = grouped.get(item.table_id);
      if (existing) {
        existing.push(item);
      } else {
        grouped.set(item.table_id, [item]);
      }
    }
    return grouped;
  }, [items]);

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        Kitchen Display
      </Typography>

      {isLoading && <RowsSkeleton count={5} />}

      {!isLoading && isError && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => refetch()}>
              Retry
            </Button>
          }
        >
          {`Could not load the kitchen display. ${errorMessage(loadError ?? new Error(GENERIC_ERROR_MESSAGE))}`}
        </Alert>
      )}

      {!isLoading && !isError && itemsByTable.size === 0 && (
        <Typography color="text.secondary">No orders in the queue</Typography>
      )}

      {!isLoading && !isError && itemsByTable.size > 0 && (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
          {Array.from(itemsByTable.entries()).map(([tableId, tableItems]) => (
            <Card key={tableId} sx={{ minWidth: 280 }}>
              <CardHeader title={`Table ${tableNumber(tableId)}`} />
              <CardContent>
                <Stack spacing={1.5}>
                  {tableItems.map((item) => {
                    const isPickingUp = pendingPickUpIds.has(item.id);
                    const isMarkingReady = pendingMarkReadyIds.has(item.id);
                    const actionError = actionErrors[item.id];
                    return (
                      <Box key={item.id}>
                        <Stack
                          direction="row"
                          spacing={1}
                          sx={{ alignItems: "center", justifyContent: "space-between" }}
                        >
                          <Typography>
                            {dishName(item.dish_id)} × {item.quantity}
                          </Typography>
                          <OrderItemStatusBadge status={item.status} />
                        </Stack>
                        {item.notes?.trim() && (
                          <Typography variant="body2" color="text.secondary">
                            {item.notes}
                          </Typography>
                        )}
                        {item.status === "pending" && (
                          <Button
                            variant="contained"
                            fullWidth
                            size="large"
                            disabled={isPickingUp}
                            onClick={() => handlePickUp(item)}
                            sx={{ marginTop: 1 }}
                          >
                            Pick up
                          </Button>
                        )}
                        {item.status === "in_preparation" && (
                          <Button
                            variant="contained"
                            fullWidth
                            size="large"
                            disabled={isMarkingReady}
                            onClick={() => handleMarkReady(item)}
                            sx={{ marginTop: 1 }}
                          >
                            Mark ready
                          </Button>
                        )}
                        {actionError && (
                          <Typography variant="body2" color="error.main" sx={{ marginTop: 0.5 }}>
                            {actionError}
                          </Typography>
                        )}
                      </Box>
                    );
                  })}
                </Stack>
              </CardContent>
            </Card>
          ))}
        </Box>
      )}
    </Box>
  );
}
