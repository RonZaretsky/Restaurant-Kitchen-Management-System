import { useNavigate } from "react-router";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";

import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useOpenTable } from "../../services/orderService";
import { useTables } from "../../services/tableService";
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
 * Only an `available` tile is an open target: clicking it opens the Table
 * into a new Order and navigates to its detail page (AC1). An occupied or
 * reserved tile carries no click handler at all (AC2), it exists only to
 * show the status badge, matching key-tables.html's read-only tiles for
 * those two states.
 *
 * @param table - The Table this tile describes.
 * @param onOpen - Called with this Table's id when an available tile is clicked.
 * @param disabled - Whether any open request is currently in flight, shared
 *   page-wide across every tile so a second click cannot open a different
 *   Table while the first request is still resolving.
 * @returns The tile for this Table.
 */
function TableTile({
  table,
  onOpen,
  disabled,
}: {
  table: Table;
  onOpen: (tableId: number) => void;
  disabled: boolean;
}) {
  const isAvailable = table.status === "available";
  const badgeColor =
    table.status === "available" ? "success" : table.status === "reserved" ? "info" : "default";

  const content = (
    <Box sx={{ padding: 2 }}>
      <Typography variant="subtitle1">{`Table ${table.table_number}`}</Typography>
      <Chip size="small" label={table.status} color={badgeColor} sx={{ marginTop: 1 }} />
    </Box>
  );

  if (!isAvailable) {
    return <Card variant="outlined">{content}</Card>;
  }

  return (
    <Card variant="outlined">
      <CardActionArea onClick={() => onOpen(table.id)} disabled={disabled}>
        {content}
      </CardActionArea>
    </Card>
  );
}

/**
 * The Waiter's Tables grid (Story 3.1).
 *
 * Every Restaurant Table rendered as a tile with its status badge
 * (AC3). Clicking an available tile opens it into a new Order (AC1) and
 * navigates to its detail page; an occupied or reserved tile has no open
 * affordance (AC2). Reuses `tableService.ts`'s existing `useTables()`
 * (Story 2.4's `GET /api/tables`, widened in this story to permit a Waiter),
 * rather than adding a second Table-list endpoint or hook.
 *
 * @returns The Tables page.
 */
export function TablesPage() {
  const navigate = useNavigate();
  const { data: tables, isLoading, isError, error, refetch } = useTables();
  const openMutation = useOpenTable();

  const handleOpen = (tableId: number) => {
    openMutation.mutate(tableId, {
      onSuccess: () => navigate(`/waiter/tables/${tableId}`),
    });
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
              disabled={openMutation.isPending}
            />
          ))}
        </Box>
      )}
    </>
  );
}
