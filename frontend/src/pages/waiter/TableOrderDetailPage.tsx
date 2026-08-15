import { useEffect, useState, type FormEvent } from "react";
import { Link as RouterLink, useParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { OrderItemStatusBadge } from "../../components/orders/OrderItemStatusBadge";
import { useRealtime } from "../../components/shell/RealtimeProvider";
import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useDishes } from "../../services/menuService";
import {
  orderItemsQueryKey,
  useAddOrderItem,
  useOrderForTable,
  useOrderItems,
} from "../../services/orderService";
import { useTables } from "../../services/tableService";
import { MAX_ORDER_ITEM_QUANTITY } from "../../types/order";

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

/** Shown when the quantity field holds something outside 1..MAX_ORDER_ITEM_QUANTITY. */
const INVALID_QUANTITY_MESSAGE = `Enter a whole number from 1 to ${MAX_ORDER_ITEM_QUANTITY}`;

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
 * Parses a route param that must be a positive whole number.
 *
 * Deliberately stricter than `Number()`, which turns "abc" into NaN and both ""
 * and " " into 0. A NaN would otherwise reach the heading as the literal text
 * "Table NaN" and be sent to the server as a request that can only ever 422.
 *
 * @param raw - The raw route param, or undefined if absent.
 * @returns The parsed id, or null if the param is not a usable one.
 */
function parseRouteId(raw: string | undefined): number | null {
  if (raw === undefined || !/^\d+$/.test(raw)) {
    return null;
  }
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

/**
 * Parses a field that must hold a quantity within the allowed range.
 *
 * Mirrors the backend's own `MAX_ORDER_ITEM_QUANTITY` bound, so an over-cap
 * value is refused here rather than coming back as a raw Pydantic 422 string.
 *
 * @param raw - The raw text from the input.
 * @returns The parsed quantity, or null if it is outside the allowed range.
 */
function parseQuantity(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  const parsed = Number(trimmed);
  return parsed > 0 && parsed <= MAX_ORDER_ITEM_QUANTITY ? parsed : null;
}

/**
 * Formats a stored price for display.
 *
 * `price_at_add` arrives as a Decimal-as-string, so it is shown as-is rather
 * than parsed through a float that could lose precision. Currency symbol per
 * the Table/Order detail mockup.
 *
 * @param priceAtAdd - The item's stored price, as sent by the API.
 * @returns The price with its currency symbol.
 */
function formatPrice(priceAtAdd: string): string {
  return `${priceAtAdd} ₪`;
}

/**
 * The Table/Order detail surface (Story 3.2).
 *
 * Reached by table_id alone (`/waiter/tables/:tableId`), so the first thing this page does is
 * resolve that id to its currently open Order (`useOrderForTable`), a read this story adds since
 * nothing before it could fetch an existing Order. Everything else, the add-dish form and the
 * Order Item list, depends on that Order's id.
 *
 * Loading/error state is combined across every query the page depends on, per the "combine every
 * query" rule Story 2.5's review established. One failure is deliberately excluded: a 404 from
 * the order lookup is not a transport failure, it means this Table simply has no Order open on it
 * right now, which is a legitimate state reachable by URL and gets its own message rather than a
 * Retry button that could never succeed.
 *
 * No actions column on the Order Item rows (edit/cancel is Story 3.4), no live updates (Story
 * 3.3), no Close order bar (a later FR-8 story). Only the add-dish form and a read-only item list
 * with status badges, per this story's own scope note.
 *
 * @returns The Table/Order detail page.
 */
export function TableOrderDetailPage() {
  const { tableId } = useParams<{ tableId: string }>();
  const parsedTableId = parseRouteId(tableId);
  const queryClient = useQueryClient();
  const { subscribe } = useRealtime();

  const [dishId, setDishId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [notes, setNotes] = useState("");

  const orderQuery = useOrderForTable(parsedTableId);
  const { data: order } = orderQuery;
  const itemsQuery = useOrderItems(order?.id);
  const { data: items } = itemsQuery;

  // Story 3.3: Observer/Pub-Sub. This component subscribes to the
  // order.item_added event OrderService publishes without knowing which
  // Waiter's action triggered it, so any Waiter adding an item to any Order
  // updates this page live if it happens to be this Order (AC2/AC3).
  // Page-wide subscription, not filtered to this order's id before
  // invalidating: invalidateQueries only refetches queries that actually
  // match the key, so invalidating a key for an order this page is not
  // showing is a harmless no-op, not a bug. Guarded on order?.id being
  // resolved, though: before that, invalidating orderItemsQueryKey(undefined)
  // would target a key nothing reads, silently missing a live update that
  // arrives in the narrow window before this page's own Order lookup
  // settles.
  useEffect(() => {
    if (order?.id === undefined) {
      return undefined;
    }
    return subscribe("order.item_added", () => {
      void queryClient.invalidateQueries({ queryKey: orderItemsQueryKey(order.id) });
    });
  }, [subscribe, queryClient, order?.id]);
  const dishesQuery = useDishes();
  const { data: dishes } = dishesQuery;
  // Reused rather than fetched per-table: the Tables grid this page is reached from has already
  // populated the same cache key, and there is no single-table GET endpoint to call instead.
  const tablesQuery = useTables();
  const { data: tables } = tablesQuery;
  const addItemMutation = useAddOrderItem(order?.id);

  // A Table exists but has nothing open on it. Split out of isError so it can be
  // presented as the state it is, not as a failed request.
  const hasNoOpenOrder =
    orderQuery.isError && orderQuery.error instanceof ApiError && orderQuery.error.status === 404;

  const isLoading =
    orderQuery.isLoading || itemsQuery.isLoading || dishesQuery.isLoading || tablesQuery.isLoading;
  const isError =
    (orderQuery.isError && !hasNoOpenOrder) ||
    itemsQuery.isError ||
    dishesQuery.isError ||
    tablesQuery.isError;
  const firstError =
    (hasNoOpenOrder ? undefined : orderQuery.error) ??
    itemsQuery.error ??
    dishesQuery.error ??
    tablesQuery.error;

  // Only refetches queries that are actually enabled. refetch() bypasses a query's own
  // `enabled` gate, so refetching blindly would fire /api/orders/undefined/items and
  // surface its 422 as the reason the page failed.
  const refetchAll = () => {
    if (parsedTableId !== null) {
      void orderQuery.refetch();
    }
    if (order?.id !== undefined) {
      void itemsQuery.refetch();
    }
    void dishesQuery.refetch();
    void tablesQuery.refetch();
  };

  const tableNumber = tables?.find((table) => table.id === parsedTableId)?.table_number;
  const heading = tableNumber === undefined ? "Table" : `Table ${tableNumber}`;

  const dishName = (dishIdValue: number) =>
    dishes?.find((dish) => dish.id === dishIdValue)?.name ?? `#${dishIdValue}`;

  const parsedQuantity = parseQuantity(quantity);
  const isQuantityInvalid = quantity !== "" && parsedQuantity === null;
  const hasDishes = dishes !== undefined && dishes.length > 0;
  const canSubmit =
    order !== undefined && dishId !== "" && parsedQuantity !== null && !addItemMutation.isPending;

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

  if (parsedTableId === null) {
    return (
      <>
        <Typography variant="h5" component="h1" gutterBottom>
          Table
        </Typography>
        <Alert severity="warning">
          {`That table link is not valid. `}
          <Link component={RouterLink} to="/waiter/tables">
            Back to Tables
          </Link>
        </Alert>
      </>
    );
  }

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        {heading}
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

      {!isLoading && !isError && hasNoOpenOrder && (
        <Alert severity="info">
          {`This table has no open order. `}
          <Link component={RouterLink} to="/waiter/tables">
            Back to Tables
          </Link>
          {` to open it.`}
        </Alert>
      )}

      {!isLoading && !isError && order && dishes && (
        <>
          {!hasDishes && (
            <Alert severity="info" sx={{ marginBottom: 2 }}>
              No dishes on the menu yet, so there is nothing to add to this order.
            </Alert>
          )}

          {hasDishes && (
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
                  <MenuItem key={dish.id} value={String(dish.id)} disabled={!dish.is_available}>
                    {dish.is_available ? dish.name : `${dish.name} (unavailable)`}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                size="small"
                label="Qty"
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
                error={isQuantityInvalid}
                helperText={isQuantityInvalid ? INVALID_QUANTITY_MESSAGE : undefined}
                slotProps={{ htmlInput: { inputMode: "numeric" } }}
                sx={{ width: 150 }}
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

              {/* The reason the submit is dead, as visible text rather than a Tooltip,
                  per the standing rule that a disabled control states its own reason. */}
              {!canSubmit && !addItemMutation.isPending && (
                <Typography variant="caption" color="text.secondary" sx={{ width: "100%" }}>
                  {dishId === "" ? "Choose a dish to add." : INVALID_QUANTITY_MESSAGE}
                </Typography>
              )}
            </Box>
          )}

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
                    {/* Trimmed, not just null-checked: an empty or whitespace-only note
                        would otherwise render as a blank cell instead of the dash. */}
                    <TableCell>{item.notes?.trim() ? item.notes : "—"}</TableCell>
                    <TableCell align="right">{item.quantity}</TableCell>
                    <TableCell align="right">{formatPrice(item.price_at_add)}</TableCell>
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
