import { useState, type FormEvent } from "react";
import { Link as RouterLink, useParams } from "react-router";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { MovementTypeChip } from "../../components/inventory/MovementTypeChip";
import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useIngredient, useRecordStockMovement, useStockMovements } from "../../services/inventoryService";
import type { MovementType } from "../../types/inventory";

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

/** Shown when the quantity field holds something invalid for the selected movement type. */
const INVALID_AMOUNT_MESSAGE = "Enter a valid, non-zero amount";

/** Movement types a Warehouse Manager or Admin may log manually. Consumption belongs to the
 * automatic pick-up deduction path only, never a manual input (the backend rejects it too). */
type LoggableMovementType = Exclude<MovementType, "consumption">;

const MOVEMENT_TYPE_OPTIONS: LoggableMovementType[] = ["purchase", "waste", "adjustment"];

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
 * and " " into 0.
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

/** A positive decimal amount, for purchase/waste (magnitude only, direction is implied). */
function parsePositiveAmount(raw: string): string | null {
  const trimmed = raw.trim();
  if (!/^\d+(\.\d+)?$/.test(trimmed) || Number(trimmed) === 0) {
    return null;
  }
  return trimmed;
}

/** An optionally-signed, non-zero decimal amount, for adjustment. */
function parseAdjustmentAmount(raw: string): string | null {
  const trimmed = raw.trim();
  if (!/^-?\d+(\.\d+)?$/.test(trimmed) || Number(trimmed) === 0) {
    return null;
  }
  return trimmed;
}

/**
 * The Ingredient detail surface.
 *
 * Reached by ingredient id alone (`/warehouse/ingredients/:ingredientId`). Shows the
 * Ingredient's stat cards (current stock, minimum threshold), a log-movement form
 * (Purchase/Waste/Adjustment only), and the movement history table with the
 * neutral-palette type chip. Deliberately excludes the shortage banner and
 * danger-styled stat cards, which belong to the Alerts and stock-levels surfaces.
 *
 * @returns The Ingredient detail page.
 */
export function IngredientDetailPage() {
  const { ingredientId } = useParams<{ ingredientId: string }>();
  const parsedIngredientId = parseRouteId(ingredientId);

  const [movementType, setMovementType] = useState<LoggableMovementType | "">("");
  const [quantity, setQuantity] = useState("");
  const [notes, setNotes] = useState("");

  const ingredientQuery = useIngredient(parsedIngredientId);
  const { data: ingredient } = ingredientQuery;
  const movementsQuery = useStockMovements(parsedIngredientId);
  const { data: movements } = movementsQuery;
  const recordMutation = useRecordStockMovement(parsedIngredientId);

  const isNotFound =
    ingredientQuery.isError && ingredientQuery.error instanceof ApiError && ingredientQuery.error.status === 404;

  const isLoading = ingredientQuery.isLoading || movementsQuery.isLoading;
  const isError = (ingredientQuery.isError && !isNotFound) || (movementsQuery.isError && !isNotFound);
  const firstError = (isNotFound ? undefined : ingredientQuery.error) ?? movementsQuery.error;

  const refetchAll = () => {
    void ingredientQuery.refetch();
    void movementsQuery.refetch();
  };

  const parsedQuantity =
    movementType === "adjustment"
      ? parseAdjustmentAmount(quantity)
      : movementType === "purchase" || movementType === "waste"
        ? parsePositiveAmount(quantity)
        : null;
  const isQuantityInvalid = quantity !== "" && movementType !== "" && parsedQuantity === null;

  const canSubmit = movementType !== "" && parsedQuantity !== null && !recordMutation.isPending;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // Re-checks the full predicate rather than a subset. A disabled button is not
    // authoritative: Enter submits a form regardless. `!movementType` (not
    // `movementType === ""`), matching IngredientsPage.tsx's `handleCreate`
    // precedent: canSubmit's own `movementType !== ""` clause lets TS's
    // control-flow analysis of aliased conditions narrow movementType to
    // exclude "" already by this point, so a literal `===` re-comparison
    // against "" is flagged TS2367 ("no overlap") by `tsc -b`.
    if (!canSubmit || !movementType || parsedQuantity === null) {
      return;
    }
    const trimmedNotes = notes.trim();
    recordMutation.mutate(
      {
        movement_type: movementType,
        quantity: parsedQuantity,
        notes: trimmedNotes === "" ? null : trimmedNotes,
      },
      {
        onSuccess: () => {
          setMovementType("");
          setQuantity("");
          setNotes("");
        },
      },
    );
  };

  if (parsedIngredientId === null) {
    return (
      <>
        <Typography variant="h5" component="h1" gutterBottom>
          Ingredient
        </Typography>
        <Alert severity="warning">
          {`That ingredient link is not valid. `}
          <Link component={RouterLink} to="/warehouse/ingredients">
            Back to Ingredients
          </Link>
        </Alert>
      </>
    );
  }

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        {ingredient ? ingredient.name : "Ingredient"}
      </Typography>

      {isLoading && <RowsSkeleton count={5} />}

      {!isLoading && isNotFound && (
        <Alert severity="warning">
          {`That ingredient link is not valid. `}
          <Link component={RouterLink} to="/warehouse/ingredients">
            Back to Ingredients
          </Link>
        </Alert>
      )}

      {!isLoading && isError && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={refetchAll}>
              Retry
            </Button>
          }
        >
          {`Could not load the ingredient. ${firstError instanceof ApiError ? firstError.message : "Try again."}`}
        </Alert>
      )}

      {!isLoading && !isError && !isNotFound && ingredient && (
        <>
          <Stack direction="row" spacing={2} sx={{ marginBottom: 3 }}>
            <Card variant="outlined" sx={{ minWidth: 180 }}>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Current stock
                </Typography>
                <Typography variant="h6">{`${ingredient.current_stock} ${ingredient.unit}`}</Typography>
              </CardContent>
            </Card>
            <Card variant="outlined" sx={{ minWidth: 180 }}>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Minimum threshold
                </Typography>
                <Typography variant="h6">{`${ingredient.min_stock_threshold} ${ingredient.unit}`}</Typography>
              </CardContent>
            </Card>
          </Stack>

          <Box
            component="form"
            onSubmit={handleSubmit}
            sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "flex-start", marginBottom: 3 }}
          >
            <TextField
              select
              size="small"
              label="Movement type"
              value={movementType}
              onChange={(event) => setMovementType(event.target.value as LoggableMovementType)}
              sx={{ minWidth: 160 }}
            >
              {MOVEMENT_TYPE_OPTIONS.map((option) => (
                <MenuItem key={option} value={option}>
                  {option.charAt(0).toUpperCase() + option.slice(1)}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              label={`Quantity (${ingredient.unit})`}
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              error={isQuantityInvalid}
              helperText={isQuantityInvalid ? INVALID_AMOUNT_MESSAGE : undefined}
              slotProps={{ htmlInput: { inputMode: "decimal" } }}
            />
            <TextField
              size="small"
              multiline
              label="Note (optional)"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
            <Button type="submit" variant="contained" disabled={!canSubmit}>
              Log movement
            </Button>
          </Box>

          {recordMutation.isError && (
            <Alert severity="error" sx={{ marginBottom: 2 }}>
              {errorMessage(recordMutation.error)}
            </Alert>
          )}

          {movements?.length === 0 && <Typography color="text.secondary">No stock movements yet</Typography>}

          {movements && movements.length > 0 && (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Type</TableCell>
                  <TableCell>Quantity</TableCell>
                  <TableCell>Recorded by</TableCell>
                  <TableCell>Note</TableCell>
                  <TableCell>When</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {movements.map((movement) => (
                  <TableRow key={movement.id}>
                    <TableCell>
                      <MovementTypeChip type={movement.movement_type} />
                    </TableCell>
                    <TableCell>
                      <Typography
                        component="span"
                        color={movement.quantity_change.startsWith("-") ? "error" : "success"}
                      >
                        {`${movement.quantity_change.startsWith("-") ? "" : "+"}${movement.quantity_change} ${ingredient.unit}`}
                      </Typography>
                    </TableCell>
                    <TableCell>{`User #${movement.performed_by}`}</TableCell>
                    <TableCell>{movement.notes?.trim() ? movement.notes : "—"}</TableCell>
                    <TableCell>{new Date(movement.timestamp).toLocaleString()}</TableCell>
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
