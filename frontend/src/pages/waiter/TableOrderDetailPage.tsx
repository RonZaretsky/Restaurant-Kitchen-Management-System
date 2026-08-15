import { useState, type FormEvent } from "react";
import { useParams } from "react-router";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { OrderItemStatusBadge } from "../../components/orders/OrderItemStatusBadge";
import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useDishes } from "../../services/menuService";
import { useAddOrderItem, useOrderForTable, useOrderItems } from "../../services/orderService";

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

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
  return GENERIC_ERROR_MESSAGE;
}

/**
 * Parses a field that must hold a positive whole number.
 *
 * @param raw - The raw text from the input.
 * @returns The parsed integer, or null if the text is not a positive whole number.
 */
function parsePositiveQuantity(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

/**
 * The Table/Order detail surface (Story 3.2).
 *
 * Reached by table_id alone (`/waiter/tables/:tableId`), so the first thing this page does is
 * resolve that id to its currently open Order (`useOrderForTable`), a read this story adds since
 * nothing before it could fetch an existing Order. Everything else, the add-dish form and the
 * Order Item list, depends on that Order's id.
 *
 * Loading/error state is combined across all three queries (order, items, dishes): the add-dish
 * form's picker depends on `useDishes()` and the item list depends on `useOrderItems()`, so a
 * failure in either must still surface an error rather than silently leaving that part blank.
 *
 * No actions column on the Order Item rows (edit/cancel is Story 3.4), no live updates (Story
 * 3.3), no Close order bar (a later FR-8 story). Only the add-dish form and a read-only item list
 * with status badges, per this story's own scope note.
 *
 * @returns The Table/Order detail page.
 */
export function TableOrderDetailPage() {
  const { tableId } = useParams<{ tableId: string }>();
  const parsedTableId = Number(tableId);

  const [dishId, setDishId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [notes, setNotes] = useState("");

  const orderQuery = useOrderForTable(parsedTableId);
  const { data: order } = orderQuery;
  const itemsQuery = useOrderItems(order?.id);
  const { data: items } = itemsQuery;
  const dishesQuery = useDishes();
  const { data: dishes } = dishesQuery;
  const addItemMutation = useAddOrderItem(order?.id);

  const isLoading = orderQuery.isLoading || itemsQuery.isLoading || dishesQuery.isLoading;
  const isError = orderQuery.isError || itemsQuery.isError || dishesQuery.isError;
  const firstError = orderQuery.error ?? itemsQuery.error ?? dishesQuery.error;
  const refetchAll = () => {
    void orderQuery.refetch();
    void itemsQuery.refetch();
    void dishesQuery.refetch();
  };

  const dishName = (dishIdValue: number) =>
    dishes?.find((dish) => dish.id === dishIdValue)?.name ?? `#${dishIdValue}`;

  const parsedQuantity = parsePositiveQuantity(quantity);
  const canSubmit = order !== undefined && dishId !== "" && parsedQuantity !== null && !addItemMutation.isPending;

  const handleAddItem = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // Re-checks the full predicate rather than a subset. A disabled button is
    // not authoritative: Enter submits a form regardless, so anything missing
    // here is a request that ships with no dish selected or an invalid quantity.
    if (!canSubmit || parsedQuantity === null) {
      return;
    }
    const trimmedNotes = notes.trim();
    addItemMutation.mutate(
      {
        dish_id: Number(dishId),
        quantity: parsedQuantity,
        notes: trimmedNotes === "" ? undefined : trimmedNotes,
      },
      {
        onSuccess: () => {
          setDishId("");
          setQuantity("1");
          setNotes("");
        },
      },
    );
  };

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        {`Table ${parsedTableId}`}
      </Typography>

      {isLoading && <RowsSkeleton count={5} />}

      {!isLoading && isError && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={refetchAll}>
              Retry
            </Button>
          }
        >
          {`Could not load the order. ${firstError instanceof ApiError ? firstError.message : "Try again."}`}
        </Alert>
      )}

      {!isLoading && !isError && order && dishes && (
        <>
          <Box
            component="form"
            onSubmit={handleAddItem}
            sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "flex-start", marginBottom: 3 }}
          >
            <TextField
              select
              size="small"
              label="Dish"
              value={dishId}
              onChange={(event) => setDishId(event.target.value)}
              sx={{ minWidth: 200 }}
            >
              {dishes.map((dish) => (
                <MenuItem key={dish.id} value={String(dish.id)}>
                  {dish.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              label="Qty"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              error={quantity !== "" && parsedQuantity === null}
              slotProps={{ htmlInput: { inputMode: "numeric" } }}
              sx={{ width: 90 }}
            />
            <TextField
              size="small"
              label="Note (optional)"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
            <Button type="submit" variant="contained" disabled={!canSubmit}>
              Add to order
            </Button>
          </Box>

          {addItemMutation.isError && (
            <Alert severity="error" sx={{ marginBottom: 2 }}>
              {errorMessage(addItemMutation.error)}
            </Alert>
          )}

          {items?.length === 0 && <Typography color="text.secondary">No items added yet.</Typography>}

          {items && items.length > 0 && (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Status</TableCell>
                  <TableCell>Dish</TableCell>
                  <TableCell>Note</TableCell>
                  <TableCell align="right">Qty</TableCell>
                  <TableCell align="right">Price</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <OrderItemStatusBadge status={item.status} />
                    </TableCell>
                    <TableCell>{dishName(item.dish_id)}</TableCell>
                    <TableCell>{item.notes ?? "—"}</TableCell>
                    <TableCell align="right">{item.quantity}</TableCell>
                    <TableCell align="right">{item.price_at_add}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}
    </>
  );
}
