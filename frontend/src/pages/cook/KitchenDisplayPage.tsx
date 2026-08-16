import { useEffect, useMemo } from "react";
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

  const isLoading = isItemsLoading || isTablesLoading || isDishesLoading;
  const isError = isItemsError || isTablesError || isDishesError;
  const loadError = itemsError ?? tablesError ?? dishesError;
  const refetch = () => {
    void refetchItems();
    void refetchTables();
    void refetchDishes();
  };

  useEffect(() => {
    return subscribe("order.item_added", () => {
      void queryClient.invalidateQueries({ queryKey: KITCHEN_ITEMS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: TABLES_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: DISHES_QUERY_KEY });
    });
  }, [subscribe, queryClient]);

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
                  {tableItems.map((item) => (
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
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          ))}
        </Box>
      )}
    </Box>
  );
}
