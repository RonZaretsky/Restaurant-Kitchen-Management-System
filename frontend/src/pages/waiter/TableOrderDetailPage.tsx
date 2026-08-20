import { useEffect, useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router";
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
  orderForTableQueryKey,
  orderItemsQueryKey,
  useAddOrderItem,
  useCancelOrderItem,
  useCloseOrder,
  useEditOrderItem,
  useMarkOrderServed,
  useOrderForTable,
  useOrderItems,
} from "../../services/orderService";
import { useTables } from "../../services/tableService";
import { MAX_ORDER_ITEM_QUANTITY, type Order, type OrderItem } from "../../types/order";

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
 * Computes the Order total client-side, from the already-fetched item list (Story 5.4, AD-7).
 *
 * The backend only computes/stores `total_amount` at close time (it is null before then), so the
 * pre-close total shown here is derived the same way the server will eventually compute it: the
 * sum of `price_at_add x quantity` over non-cancelled items only.
 *
 * @param items - The Order's current item list.
 * @returns The computed total, formatted with two decimal places (no currency symbol).
 */
function computeClientSideTotal(items: OrderItem[]): string {
  const total = items
    .filter((item) => item.status !== "cancelled")
    .reduce((sum, item) => sum + Number(item.price_at_add) * item.quantity, 0);
  return total.toFixed(2);
}

/**
 * The Order total / Mark served / Close bar (Story 5.4), always visible once the Order is
 * loaded, per `EXPERIENCE.md`'s "Order total / Close action" row.
 *
 * The displayed total is the server's own stored `total_amount` once the Order is `closed` (the
 * authoritative, immutable value, AC5); before that it is computed client-side from `items`
 * (AD-7). Mark served mirrors the backend's own guard (`ready`, or `pending` with zero
 * non-cancelled items, AC1/AC2) — checked against the already-fetched `items` list directly
 * rather than trusting `order.status === "pending"` alone, since the Order and item-list queries
 * can momentarily disagree (independent TanStack Query caches, refreshed by different live
 * events). Close is enabled only once `served` (AC4) and applies immediately with no confirm step
 * (AC6, UX-DR12 contrast — unlike the cancel path above, this is not a data-loss risk).
 *
 * @param order - The Order this bar describes.
 * @param items - The Order's current item list, used for the pre-close total.
 * @returns The total bar with its Mark served / Close actions.
 */
function OrderTotalBar({ order, items }: { order: Order; items: OrderItem[] }) {
  const navigate = useNavigate();
  const markServedMutation = useMarkOrderServed(order.id, order.table_id);
  const closeMutation = useCloseOrder(order.id);

  const canMarkServed =
    order.status === "ready" ||
    (order.status === "pending" && items.every((item) => item.status === "cancelled"));
  const canClose = order.status === "served";
  const displayedTotal = order.status === "closed" && order.total_amount !== null
    ? order.total_amount
    : computeClientSideTotal(items);

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 2,
        marginTop: 3,
        padding: 2,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
      }}
    >
      <Box>
        <Typography variant="caption" color="text.secondary">
          Order total
        </Typography>
        <Typography variant="h6">{formatPrice(displayedTotal)}</Typography>
      </Box>
      <Box sx={{ display: "flex", gap: 1 }}>
        <Button
          variant="outlined"
          onClick={() => markServedMutation.mutate()}
          disabled={!canMarkServed || markServedMutation.isPending}
        >
          Mark served
        </Button>
        <Button
          variant="contained"
          onClick={() => closeMutation.mutate(undefined, { onSuccess: () => navigate("/waiter/tables") })}
          disabled={!canClose || closeMutation.isPending}
        >
          Close order
        </Button>
      </Box>
      {markServedMutation.isError && (
        <Alert severity="error" sx={{ width: "100%" }}>
          {errorMessage(markServedMutation.error)}
        </Alert>
      )}
      {closeMutation.isError && (
        <Alert severity="error" sx={{ width: "100%" }}>
          {errorMessage(closeMutation.error)}
        </Alert>
      )}
    </Box>
  );
}

/**
 * One row of the Order Item table, owning its own local edit/confirm state (Story 3.4).
 *
 * Mirrors `TablesSetupPage.tsx`'s `TableListRow`/`UsersPage.tsx`'s `UserListRow` shape: editing or
 * confirming one row must not re-render or reset the whole list, and each row gets its own
 * `useEditOrderItem`/`useCancelOrderItem` mutation instance (not one shared across every row),
 * so editing one item and cancelling another are independent actions, never cross-row disabled or
 * cross-row error bleed the way a single page-level shared mutation would produce.
 *
 * Action visibility follows the ACs exactly: `pending` gets Edit + a plain Cancel (AC1/AC2, no
 * confirm needed, nothing was deducted yet); `in_preparation` gets Cancel only, behind an in-row
 * confirm reveal stating the prior stock deduction will not be restored (AC3/AC4/UX-DR12, the
 * `UsersPage.tsx` "Deactivate {name}?" in-row-reveal precedent, not a modal, this codebase has
 * never introduced one); `ready`/`cancelled` get no actions at all.
 *
 * @param item - The Order Item this row describes.
 * @param dishName - The resolved name of the item's Dish.
 * @param orderId - The Order this item belongs to, passed through to the mutations.
 * @returns The table row(s) for this Order Item (a second row when the cancel confirm is open).
 */
function OrderItemRow({
  item,
  dishName,
  orderId,
}: {
  item: OrderItem;
  dishName: string;
  orderId: number | undefined;
}) {
  const editMutation = useEditOrderItem(orderId);
  const cancelMutation = useCancelOrderItem(orderId);

  const [isEditing, setIsEditing] = useState(false);
  const [isConfirmingCancel, setIsConfirmingCancel] = useState(false);
  const [draftQuantity, setDraftQuantity] = useState(String(item.quantity));
  const [draftNotes, setDraftNotes] = useState(item.notes ?? "");

  // Resyncs from the server only while not mid-edit, same guarded pattern
  // TablesSetupPage's TableListRow uses, so a background refetch cannot
  // clobber what the Waiter is actively typing.
  useEffect(() => {
    if (!isEditing) {
      setDraftQuantity(String(item.quantity));
      setDraftNotes(item.notes ?? "");
    }
  }, [item.quantity, item.notes, isEditing]);

  const parsedDraftQuantity = parseQuantity(draftQuantity);
  const isDraftQuantityInvalid = draftQuantity !== "" && parsedDraftQuantity === null;

  const handleSaveEdit = () => {
    if (parsedDraftQuantity === null) {
      return;
    }
    const trimmedNotes = draftNotes.trim();
    editMutation.mutate(
      {
        itemId: item.id,
        payload: { quantity: parsedDraftQuantity, notes: trimmedNotes === "" ? null : trimmedNotes },
      },
      { onSuccess: () => setIsEditing(false) },
    );
  };

  const handleCancelItem = () => {
    cancelMutation.mutate(item.id, { onSuccess: () => setIsConfirmingCancel(false) });
  };

  const handleDiscardEdit = () => {
    setIsEditing(false);
    editMutation.reset();
  };

  const handleBackFromConfirm = () => {
    setIsConfirmingCancel(false);
    cancelMutation.reset();
  };

  const rowError = editMutation.isError
    ? errorMessage(editMutation.error)
    : cancelMutation.isError
      ? errorMessage(cancelMutation.error)
      : undefined;

  return (
    <>
      <TableRow>
        <TableCell>
          <OrderItemStatusBadge status={item.status} />
        </TableCell>
        <TableCell>{dishName}</TableCell>
        <TableCell>
          {isEditing && item.status === "pending" ? (
            <TextField
              size="small"
              label="Note (optional)"
              value={draftNotes}
              onChange={(event) => setDraftNotes(event.target.value)}
            />
          ) : item.notes?.trim() ? (
            item.notes
          ) : (
            "—"
          )}
        </TableCell>
        <TableCell align="right">
          {isEditing && item.status === "pending" ? (
            <TextField
              size="small"
              label="Qty"
              value={draftQuantity}
              onChange={(event) => setDraftQuantity(event.target.value)}
              error={isDraftQuantityInvalid}
              helperText={isDraftQuantityInvalid ? INVALID_QUANTITY_MESSAGE : undefined}
              slotProps={{ htmlInput: { inputMode: "numeric" } }}
              sx={{ width: 110 }}
            />
          ) : (
            item.quantity
          )}
        </TableCell>
        <TableCell align="right">{formatPrice(item.price_at_add)}</TableCell>
        <TableCell align="right">
          {item.status === "pending" && !isEditing && (
            <>
              <Button size="small" onClick={() => setIsEditing(true)}>
                Edit
              </Button>
              <Button size="small" color="error" onClick={handleCancelItem} disabled={cancelMutation.isPending}>
                Cancel
              </Button>
            </>
          )}
          {item.status === "pending" && isEditing && (
            <>
              <Button
                size="small"
                variant="contained"
                onClick={handleSaveEdit}
                disabled={parsedDraftQuantity === null || editMutation.isPending}
              >
                Save
              </Button>
              <Button size="small" onClick={handleDiscardEdit} disabled={editMutation.isPending}>
                Back
              </Button>
            </>
          )}
          {item.status === "in_preparation" && !isConfirmingCancel && (
            <Button size="small" color="error" onClick={() => setIsConfirmingCancel(true)}>
              Cancel
            </Button>
          )}
        </TableCell>
      </TableRow>
      {item.status === "in_preparation" && isConfirmingCancel && (
        <TableRow>
          <TableCell colSpan={6} sx={{ borderBottom: "none" }}>
            <Alert
              severity="warning"
              action={
                <Box sx={{ display: "flex", gap: 1 }}>
                  <Button
                    size="small"
                    color="inherit"
                    onClick={handleBackFromConfirm}
                    disabled={cancelMutation.isPending}
                  >
                    Back
                  </Button>
                  <Button
                    size="small"
                    color="error"
                    onClick={handleCancelItem}
                    disabled={cancelMutation.isPending}
                  >
                    Confirm cancel
                  </Button>
                </Box>
              }
            >
              Stock already deducted for this item will not be restored. Cancel anyway?
            </Alert>
          </TableCell>
        </TableRow>
      )}
      {rowError && (
        <TableRow>
          <TableCell colSpan={6} sx={{ borderBottom: "none" }}>
            <Alert severity="error">{rowError}</Alert>
          </TableCell>
        </TableRow>
      )}
    </>
  );
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
 * Story 3.4 added the Actions column: Edit + Cancel on a pending row, Cancel-behind-a-confirm on
 * an in_preparation row, nothing on ready/cancelled. No Close order bar yet (a later FR-8 story).
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
  // Story 5.2: order.item_status_changed is a second, distinct event (a Cook's
  // pick-up/mark-ready transition, not a new item), subscribed to alongside
  // order.item_added rather than folded into one subscribe() call, since
  // useRealtime()'s subscribe is per-event-name. Both invalidate the same
  // key: this page never inspects the payload directly, only refetches.
  // Story 5.3: order.status_changed is a third, distinct event (the Order's own derived
  // status, not an item), invalidating this page's `useOrderForTable` query key instead —
  // that Order object is what first makes `.status` a real, changing field this story adds,
  // so it needs the same live-refresh treatment every other query on this page already gets.
  useEffect(() => {
    if (order?.id === undefined) {
      return undefined;
    }
    const unsubscribeItemAdded = subscribe("order.item_added", () => {
      void queryClient.invalidateQueries({ queryKey: orderItemsQueryKey(order.id) });
    });
    const unsubscribeItemStatusChanged = subscribe("order.item_status_changed", () => {
      void queryClient.invalidateQueries({ queryKey: orderItemsQueryKey(order.id) });
    });
    const unsubscribeOrderStatusChanged = subscribe("order.status_changed", () => {
      void queryClient.invalidateQueries({ queryKey: orderForTableQueryKey(parsedTableId) });
    });
    return () => {
      unsubscribeItemAdded();
      unsubscribeItemStatusChanged();
      unsubscribeOrderStatusChanged();
    };
  }, [subscribe, queryClient, order?.id, parsedTableId]);
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

      {!isLoading && !isError && !hasNoOpenOrder && order && dishes && (
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
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map((item) => (
                  <OrderItemRow key={item.id} item={item} dishName={dishName(item.dish_id)} orderId={order.id} />
                ))}
              </TableBody>
            </Table>
          )}

          <OrderTotalBar order={order} items={items ?? []} />
        </>
      )}
    </>
  );
}
