import { useEffect } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
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
import { useOpenTable } from "../../services/orderService";
import { TABLES_QUERY_KEY, useTables } from "../../services/tableService";
import type { Table } from "../../types/table";

/**
 * Reads the human-readable message off a failed request.
 *
 * @param error - The error a query or mutation failed with.
 * @returns The message to display inline.
 */
function errorMessage(error: Error): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Something went wrong. Try again.";
}

/**
 * One tile of the Tables grid.
 *
 * An `available` tile opens the Table into a new Order and navigates to its
 * detail page (AC1, Story 3.1). An `occupied` tile has an already-open Order
 * on it (Story 3.2 built that detail page's real content), so it navigates
 * straight there with no open call. A `reserved` tile stays a read-only
 * status display, there is no reservation-arrival flow in v1 (PRD FR-4) so
 * nothing exists yet for a Waiter to reach by clicking it.
 *
 * @param table - The Table this tile describes.
 * @param onOpen - Called with this Table's id when an available tile is clicked.
 * @param onView - Called with this Table's id when an occupied tile is clicked.
 * @param disabled - Whether an open request is currently in flight, shared
 *   page-wide across every tile so a second click cannot open a different
 *   Table while the first request is still resolving.
 * @returns The tile for this Table.
 */
function TableTile({
  table,
  onOpen,
  onView,
  disabled,
}: {
  table: Table;
  onOpen: (tableId: number) => void;
  onView: (tableId: number) => void;
  disabled: boolean;
}) {
  const badgeColor =
    table.status === "available" ? "success" : table.status === "reserved" ? "info" : "default";

  const content = (
    <Box sx={{ padding: 2 }}>
      <Typography variant="subtitle1">{`Table ${table.table_number}`}</Typography>
      <Chip size="small" label={table.status} color={badgeColor} sx={{ marginTop: 1 }} />
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
 * The Waiter's Tables grid (Story 3.1, extended by Story 3.2 and 3.3).
 *
 * Every Restaurant Table rendered as a tile with its status badge (AC3).
 * Clicking an available tile opens it into a new Order (AC1, Story 3.1) and
 * navigates to its detail page. Clicking an occupied tile navigates straight
 * to that same detail page without opening anything, since Story 3.2 gave
 * that page real content (the Order's item list and add-dish form) — before
 * that story, an occupied tile had no click affordance at all because there
 * was nothing to see there yet. A reserved tile still has no click
 * affordance, v1 has no reservation-arrival flow. Reuses `tableService.ts`'s
 * existing `useTables()` (Story 2.4's `GET /api/tables`, widened in Story 3.1
 * to permit a Waiter), rather than adding a second Table-list endpoint or hook.
 * Subscribes to the live `table.status_changed` push (Story 3.3) so another
 * Waiter opening a Table updates this grid without a manual refresh.
 *
 * @returns The Tables page.
 */
export function TablesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { subscribe } = useRealtime();
  const { data: tables, isLoading, isError, error, refetch } = useTables();
  const openMutation = useOpenTable();

  // Story 3.3: Observer/Pub-Sub. This component subscribes to the
  // table.status_changed event OrderService publishes without knowing which
  // Waiter's action triggered it, so any Waiter opening any Table flips its
  // status live for every other connected Waiter (AC2/AC3). Invalidating
  // the existing tables query is the refetch signal, matching this
  // codebase's established invalidate-then-refetch mutation pattern rather
  // than merging the pushed payload directly into the cache.
  useEffect(() => {
    return subscribe("table.status_changed", () => {
      void queryClient.invalidateQueries({ queryKey: TABLES_QUERY_KEY });
    });
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
            <Button color="inherit" size="small" onClick={() => refetch()}>
              Retry
            </Button>
          }
        >
          {`Could not load the tables. ${errorMessage(error)}`}
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
            />
          ))}
        </Box>
      )}
    </>
  );
}
