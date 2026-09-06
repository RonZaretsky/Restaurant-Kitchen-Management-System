import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";

import { useRealtime } from "../../components/shell/RealtimeProvider";
import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { OPEN_ORDERS_QUERY_KEY, useOpenOrders, useOpenTable } from "../../services/orderService";
import { TABLES_QUERY_KEY, useTables } from "../../services/tableService";
import type { Table } from "../../types/table";

/**
 * Reads the human-readable message off a failed request.
 *
 * Accepts `Error | null` (not just `Error`) since the combined `isTablesError ||
 * isOpenOrdersError` breaks the discriminated-union narrowing TanStack Query's single-query
 * destructuring otherwise gives `error` for free — the caller now has to pass whichever of two
 * independent queries' `error` fields actually failed, and either can be null while the other
 * isn't.
 *
 * @param error - The error a query or mutation failed with, or null.
 * @returns The message to display inline.
 */
function errorMessage(error: Error | null): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Something went wrong. Try again.";
}

/**
 * One tile of the Tables grid.
 *
 * An `available` tile opens the Table into a new Order and navigates to its
 * detail page. An `occupied` tile has an already-open Order
 * on it, so it navigates
 * straight there with no open call. A `reserved` tile stays a read-only
 * status display, there is no reservation-arrival flow in v1 so
 * nothing exists yet for a Waiter to reach by clicking it.
 *
 * An `occupied` tile whose Order has reached `ready` additionally renders the
 * attention-state Chip (the same green/check treatment as a `ready`
 * OrderItemStatusBadge), layered next to the base table-status Chip,
 * never replacing it.
 *
 * @param table - The Table this tile describes.
 * @param onOpen - Called with this Table's id when an available tile is clicked.
 * @param onView - Called with this Table's id when an occupied tile is clicked.
 * @param disabled - Whether an open request is currently in flight, shared
 *   page-wide across every tile so a second click cannot open a different
 *   Table while the first request is still resolving.
 * @param isReadyForAttention - Whether this Table's open Order has reached `ready`.
 * @returns The tile for this Table.
 */
function TableTile({
  table,
  onOpen,
  onView,
  disabled,
  isReadyForAttention,
}: {
  table: Table;
  onOpen: (tableId: number) => void;
  onView: (tableId: number) => void;
  disabled: boolean;
  isReadyForAttention: boolean;
}) {
  const badgeColor =
    table.status === "available" ? "success" : table.status === "reserved" ? "info" : "default";

  const content = (
    <Box sx={{ padding: 2 }}>
      <Typography variant="subtitle1">{`Table ${table.table_number}`}</Typography>
      <Chip size="small" label={table.status} color={badgeColor} sx={{ marginTop: 1 }} />
      {isReadyForAttention && (
        <Chip
          size="small"
          icon={<CheckCircleIcon />}
          label="Ready"
          color="success"
          sx={{ marginTop: 1, marginLeft: 1 }}
        />
      )}
    </Box>
  );

  if (table.status === "reserved") {
    return <Card variant="outlined">{content}</Card>;
  }

  const onClick = table.status === "available" ? () => onOpen(table.id) : () => onView(table.id);

  return (
    <Card variant="outlined">
      <CardActionArea onClick={onClick} disabled={disabled}>
        {content}
      </CardActionArea>
    </Card>
  );
}

/**
 * The Waiter's Tables grid.
 *
 * Every Restaurant Table rendered as a tile with its status badge.
 * Clicking an available tile opens it into a new Order and
 * navigates to its detail page. Clicking an occupied tile navigates straight
 * to that same detail page without opening anything, since that page holds
 * the Order's item list and add-dish form. A reserved tile has no click
 * affordance, v1 has no reservation-arrival flow. Reuses `tableService.ts`'s
 * existing `useTables()` (`GET /api/tables`, which permits a Waiter) rather
 * than adding a second Table-list endpoint or hook.
 * Subscribes to the live `table.status_changed` push so another
 * Waiter opening a Table updates this grid without a manual refresh. A second
 * query, `useOpenOrders()` (the bulk `GET /api/orders` read), resolved client-side into a
 * table_id -> `ready` lookup so occupied tiles can render the attention-state treatment,
 * and a second live subscription, `order.status_changed`, keeping that lookup live.
 *
 * @returns The Tables page.
 */
export function TablesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { subscribe } = useRealtime();
  const {
    data: tables,
    isLoading: isTablesLoading,
    isError: isTablesError,
    error: tablesError,
    refetch: refetchTables,
  } = useTables();
  const {
    data: openOrders,
    isLoading: isOpenOrdersLoading,
    isError: isOpenOrdersError,
    error: openOrdersError,
    refetch: refetchOpenOrders,
  } = useOpenOrders();
  const openMutation = useOpenTable();

  const isLoading = isTablesLoading || isOpenOrdersLoading;
  const isError = isTablesError || isOpenOrdersError;
  // Neither query's own isError flag correlates with the other's error field once combined
  // above, so this picks whichever actually failed rather than assuming it was tablesError.
  const firstError = tablesError ?? openOrdersError;

  // Retry must refetch every dependent query, not just the "main" one (this codebase's own
  // established rule for a page driven by more than one independent query) — otherwise a
  // failure isolated to useOpenOrders() alone would leave Retry calling only the
  // already-succeeded useTables(), permanently stuck behind the error banner.
  const retryAll = () => {
    void refetchTables();
    void refetchOpenOrders();
  };

  // The set of table_ids whose open Order has reached `ready`. Only `occupied` tiles are
  // ever consulted against this set (a Table only gets an Order via open_table, gated on
  // status == available; reserved/available tiles never have one in v1), but the set itself is
  // built off every open Order regardless of Table status, cheaper than filtering first.
  const readyTableIds = useMemo(
    () => new Set((openOrders ?? []).filter((order) => order.status === "ready").map((order) => order.table_id)),
    [openOrders],
  );

  // Observer/Pub-Sub. This component subscribes to the
  // table.status_changed event OrderService publishes without knowing which
  // Waiter's action triggered it, so any Waiter opening any Table flips its
  // status live for every other connected Waiter. Invalidating
  // the existing tables query is the refetch signal, matching this
  // codebase's established invalidate-then-refetch mutation pattern rather
  // than merging the pushed payload directly into the cache.
  // order.status_changed is a second, distinct event (an Order's derived status
  // moving, not a Table's own status), invalidating the open-orders query instead so the
  // attention-state lookup above stays live.
  useEffect(() => {
    const unsubscribeTableStatusChanged = subscribe("table.status_changed", () => {
      void queryClient.invalidateQueries({ queryKey: TABLES_QUERY_KEY });
    });
    const unsubscribeOrderStatusChanged = subscribe("order.status_changed", () => {
      void queryClient.invalidateQueries({ queryKey: OPEN_ORDERS_QUERY_KEY });
    });
    return () => {
      unsubscribeTableStatusChanged();
      unsubscribeOrderStatusChanged();
    };
  }, [subscribe, queryClient]);

  const handleOpen = (tableId: number) => {
    openMutation.mutate(tableId, {
      onSuccess: () => navigate(`/waiter/tables/${tableId}`),
    });
  };

  const handleView = (tableId: number) => {
    navigate(`/waiter/tables/${tableId}`);
  };

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        Tables
      </Typography>

      {openMutation.isError && (
        <Alert severity="error" sx={{ marginBottom: 2 }}>
          {errorMessage(openMutation.error)}
        </Alert>
      )}

      {isLoading && <RowsSkeleton count={5} />}

      {isError && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={retryAll}>
              Retry
            </Button>
          }
        >
          {`Could not load the tables. ${errorMessage(firstError)}`}
        </Alert>
      )}

      {!isLoading && !isError && tables?.length === 0 && (
        <Typography color="text.secondary">No tables configured yet.</Typography>
      )}

      {!isLoading && !isError && tables && tables.length > 0 && (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
            gap: 2,
          }}
        >
          {tables.map((table) => (
            <TableTile
              key={table.id}
              table={table}
              onOpen={handleOpen}
              onView={handleView}
              disabled={openMutation.isPending}
              isReadyForAttention={table.status === "occupied" && readyTableIds.has(table.id)}
            />
          ))}
        </Box>
      )}
    </>
  );
}
