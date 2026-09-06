import { useMemo, useState, type FormEvent, type MouseEvent } from "react";
import { useNavigate } from "react-router";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TableSortLabel from "@mui/material/TableSortLabel";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import {
  useAlerts,
  useCreateIngredient,
  useDeactivateIngredient,
  useIngredients,
  useReactivateIngredient,
} from "../../services/inventoryService";
import type { Ingredient } from "../../types/inventory";
import type { Unit } from "../../types/menu";

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

/** Shown when a threshold/stock field holds something that is not a non-negative number. */
const INVALID_AMOUNT_MESSAGE = "Enter a number, zero or greater";

const UNIT_OPTIONS: Unit[] = ["kg", "liter", "piece"];

/** The four sortable columns. */
type SortableColumn = "name" | "unit" | "current_stock" | "min_stock_threshold";
type SortOrder = "asc" | "desc";

const COLUMNS: { key: SortableColumn; label: string }[] = [
  { key: "name", label: "Name" },
  { key: "unit", label: "Unit" },
  { key: "current_stock", label: "Current stock" },
  { key: "min_stock_threshold", label: "Threshold" },
];

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
 * Parses a field that must hold a non-negative decimal amount.
 *
 * Deliberately stricter than `Number()`: that coerces `""`/`" "` to 0 and
 * turns anything unparseable into `NaN`, which `JSON.stringify` then
 * serializes as `null`. Returns the trimmed string itself (not a number),
 * matching `Ingredient.current_stock`/`min_stock_threshold`'s
 * Decimal-as-string wire convention.
 *
 * @param raw - The raw text from the input.
 * @returns The trimmed amount string, or null if it is not a non-negative number.
 */
function parseNonNegativeAmount(raw: string): string | null {
  const trimmed = raw.trim();
  if (!/^\d+(\.\d+)?$/.test(trimmed)) {
    return null;
  }
  return trimmed;
}

/**
 * Compares two Ingredients by one sortable column.
 *
 * `current_stock`/`min_stock_threshold` compare numerically (parsed off their
 * Decimal-as-string wire shape), `name`/`unit` compare via `localeCompare`,
 * matching the default shortage-sort's own alphabetical tiebreak.
 *
 * @param a - The first Ingredient.
 * @param b - The second Ingredient.
 * @param column - The column to compare by.
 * @returns A negative, zero, or positive number, ascending order.
 */
function compareByColumn(a: Ingredient, b: Ingredient, column: SortableColumn): number {
  if (column === "current_stock" || column === "min_stock_threshold") {
    return Number(a[column]) - Number(b[column]);
  }
  return a[column].localeCompare(b[column]);
}

interface IngredientRowProps {
  ingredient: Ingredient;
  inShortage: boolean;
  onNavigate: () => void;
}

/**
 * One row of the Ingredients list, owning its own deactivate-confirmation state.
 *
 * Mirrors UsersPage's UserListRow: an Active/Inactive Chip plus an in-row
 * Deactivate/Reactivate action, the same
 * `"Deactivate {name}?"` inline-confirm pattern rather than a new dialog.
 * Action buttons stop click propagation so they never also trigger the row's
 * own navigate-to-detail click handler.
 *
 * @param props - The Ingredient this row displays, its shortage flag, and the
 *   navigate callback for a plain row click.
 * @returns The table row(s): the data row, plus an inline error row when a
 *   mutation on this row has failed.
 */
function IngredientRow({ ingredient, inShortage, onNavigate }: IngredientRowProps) {
  const [isConfirmingDeactivate, setIsConfirmingDeactivate] = useState(false);
  const deactivateMutation = useDeactivateIngredient();
  const reactivateMutation = useReactivateIngredient();

  const cellSx = inShortage ? { color: "error.main" } : undefined;

  const stopPropagation = (event: MouseEvent) => event.stopPropagation();

  const activeError = deactivateMutation.isError
    ? deactivateMutation.error
    : reactivateMutation.isError
      ? reactivateMutation.error
      : undefined;

  return (
    <>
      <TableRow hover onClick={onNavigate} sx={{ cursor: "pointer" }}>
        <TableCell sx={cellSx}>
          {inShortage && (
            <WarningAmberIcon
              fontSize="small"
              color="error"
              sx={{ verticalAlign: "text-bottom", marginRight: 0.5 }}
            />
          )}
          {ingredient.name}
        </TableCell>
        <TableCell sx={cellSx}>{ingredient.unit}</TableCell>
        <TableCell sx={cellSx}>{ingredient.current_stock}</TableCell>
        <TableCell sx={cellSx}>{ingredient.min_stock_threshold}</TableCell>
        <TableCell>
          <Chip
            size="small"
            label={ingredient.is_active ? "Active" : "Inactive"}
            color={ingredient.is_active ? "success" : "default"}
          />
        </TableCell>
        <TableCell align="right" onClick={stopPropagation}>
          {isConfirmingDeactivate ? (
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", justifyContent: "flex-end" }}>
              <Typography variant="caption">{`Deactivate ${ingredient.name}?`}</Typography>
              <Button
                size="small"
                variant="contained"
                color="error"
                onClick={() =>
                  deactivateMutation.mutate(ingredient.id, {
                    onSuccess: () => setIsConfirmingDeactivate(false),
                  })
                }
                disabled={deactivateMutation.isPending}
              >
                Confirm
              </Button>
              <Button
                size="small"
                onClick={() => setIsConfirmingDeactivate(false)}
                disabled={deactivateMutation.isPending}
              >
                Cancel
              </Button>
            </Box>
          ) : ingredient.is_active ? (
            <Button
              size="small"
              color="error"
              onClick={() => {
                deactivateMutation.reset();
                reactivateMutation.reset();
                setIsConfirmingDeactivate(true);
              }}
              disabled={deactivateMutation.isPending}
            >
              Deactivate
            </Button>
          ) : (
            <Button
              size="small"
              onClick={() => {
                deactivateMutation.reset();
                reactivateMutation.reset();
                reactivateMutation.mutate(ingredient.id);
              }}
              disabled={reactivateMutation.isPending}
            >
              Reactivate
            </Button>
          )}
        </TableCell>
      </TableRow>
      {activeError && (
        <TableRow>
          <TableCell colSpan={6}>
            <Alert severity="error">{errorMessage(activeError)}</Alert>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

/**
 * The Ingredients surface.
 *
 * An always-visible "Add ingredient" form and a dense-row list (Name / Unit /
 * Current stock / Threshold / Status / Actions) of every Ingredient.
 * Each row clicks through to the Ingredient detail page (stat cards,
 * log-movement form, movement history), which otherwise has no discoverable
 * entry point from this screen.
 *
 * The shortage row treatment: in-shortage rows (reusing useAlerts()'s
 * already-derived shortage list, not a second
 * current_stock < min_stock_threshold comparison here) render a
 * WarningAmberIcon plus error-colored text and sort to the top, alphabetical
 * within each group. Live
 * updates come free from AppShell.tsx's existing global
 * inventory.alerts_changed subscription invalidating the shared
 * ALERTS_QUERY_KEY this page's own useAlerts() call reads from — no second
 * subscription needed here.
 *
 * Standard MUI TableSortLabel sorting is available on all four
 * original columns: the shortage-first-then-alphabetical order above stays
 * the *initial* state (`sortColumn === null`); clicking a header switches to
 * sorting the full list by that column (asc, then desc on a repeated click of
 * the same header), and shortage highlighting keeps rendering regardless of
 * the active sort order — it is an orthogonal visual treatment, not a sort
 * key.
 *
 * A Status column (Active/Inactive Chip) and a per-row
 * Deactivate/Reactivate action mirror UsersPage's own in-row
 * confirm pattern, backed by useDeactivateIngredient/useReactivateIngredient.
 *
 * @returns The Ingredients page.
 */
export function IngredientsPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [unit, setUnit] = useState<Unit | "">("");
  const [threshold, setThreshold] = useState("");
  const [currentStock, setCurrentStock] = useState("");
  const [sortColumn, setSortColumn] = useState<SortableColumn | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc");

  const {
    data: ingredients,
    isLoading: isIngredientsLoading,
    isError: isIngredientsError,
    error: ingredientsError,
    refetch: refetchIngredients,
  } = useIngredients();
  const {
    data: alerts,
    isLoading: isAlertsLoading,
    isError: isAlertsError,
    error: alertsError,
    refetch: refetchAlerts,
  } = useAlerts();
  const createMutation = useCreateIngredient();

  const isLoading = isIngredientsLoading || isAlertsLoading;
  const isError = isIngredientsError || isAlertsError;
  const loadError = ingredientsError ?? alertsError;
  const refetch = () => {
    void refetchIngredients();
    void refetchAlerts();
  };

  const shortageIds = useMemo(() => new Set(alerts?.map((alert) => alert.id) ?? []), [alerts]);

  const handleRequestSort = (column: SortableColumn) => {
    if (sortColumn === column) {
      setSortOrder((previous) => (previous === "asc" ? "desc" : "asc"));
    } else {
      setSortColumn(column);
      setSortOrder("asc");
    }
  };

  const sortedIngredients = useMemo(() => {
    if (!ingredients) {
      return undefined;
    }
    if (sortColumn !== null) {
      const direction = sortOrder === "asc" ? 1 : -1;
      return [...ingredients].sort((a, b) => direction * compareByColumn(a, b, sortColumn));
    }
    // The default view: shortage-first, then alphabetical.
    const withShortageFlag = ingredients.map((ingredient) => ({
      ingredient,
      inShortage: shortageIds.has(ingredient.id),
    }));
    withShortageFlag.sort((a, b) => {
      if (a.inShortage !== b.inShortage) {
        return a.inShortage ? -1 : 1;
      }
      return a.ingredient.name.localeCompare(b.ingredient.name);
    });
    return withShortageFlag.map(({ ingredient }) => ingredient);
  }, [ingredients, shortageIds, sortColumn, sortOrder]);

  const parsedThreshold = parseNonNegativeAmount(threshold);
  const currentStockTrimmed = currentStock.trim();
  const parsedCurrentStock = currentStockTrimmed === "" ? null : parseNonNegativeAmount(currentStockTrimmed);
  const isCurrentStockInvalid = currentStockTrimmed !== "" && parsedCurrentStock === null;

  const canSubmit =
    name.trim() !== "" &&
    unit !== "" &&
    parsedThreshold !== null &&
    !isCurrentStockInvalid &&
    !createMutation.isPending;

  const handleCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // Re-checks the full predicate rather than a subset. A disabled button is
    // not authoritative: Enter submits a form regardless, so anything missing
    // here is a request that ships with a blank name or duplicates in flight.
    if (!canSubmit || !unit || parsedThreshold === null) {
      return;
    }
    createMutation.mutate(
      {
        name: name.trim(),
        unit,
        min_stock_threshold: parsedThreshold,
        current_stock: currentStockTrimmed === "" ? undefined : (parsedCurrentStock ?? undefined),
      },
      {
        onSuccess: () => {
          setName("");
          setUnit("");
          setThreshold("");
          setCurrentStock("");
        },
      },
    );
  };

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        Ingredients
      </Typography>
      {/* Only once the list is actually known, and gated on the same condition
          as the table below it. Truthiness alone was not enough: after a
          successful load followed by a failed refetch, isError is true while
          data still holds the stale list, so the subtitle asserted a count
          beside "Could not load the ingredients" with the table itself
          hidden. */}
      {!isLoading && !isError && ingredients && (
        <Typography color="text.secondary" gutterBottom>
          {`${ingredients.length} ${ingredients.length === 1 ? "ingredient" : "ingredients"}`}
        </Typography>
      )}

      <Box
        component="form"
        onSubmit={handleCreate}
        sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "flex-start", marginBottom: 3 }}
      >
        <TextField
          size="small"
          label="Ingredient name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          slotProps={{ htmlInput: { maxLength: 100 } }}
        />
        <TextField
          select
          size="small"
          label="Unit"
          value={unit}
          onChange={(event) => setUnit(event.target.value as Unit)}
          sx={{ minWidth: 120 }}
        >
          {UNIT_OPTIONS.map((unitOption) => (
            <MenuItem key={unitOption} value={unitOption}>
              {unitOption}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="Minimum stock threshold"
          value={threshold}
          onChange={(event) => setThreshold(event.target.value)}
          error={threshold !== "" && parsedThreshold === null}
          helperText={threshold !== "" && parsedThreshold === null ? INVALID_AMOUNT_MESSAGE : undefined}
          slotProps={{ htmlInput: { inputMode: "decimal" } }}
        />
        <TextField
          size="small"
          label="Current stock (optional)"
          value={currentStock}
          onChange={(event) => setCurrentStock(event.target.value)}
          error={isCurrentStockInvalid}
          helperText={isCurrentStockInvalid ? INVALID_AMOUNT_MESSAGE : undefined}
          slotProps={{ htmlInput: { inputMode: "decimal" } }}
        />
        <Button type="submit" variant="contained" disabled={!canSubmit}>
          Add ingredient
        </Button>
      </Box>

      {createMutation.isError && (
        <Alert severity="error" sx={{ marginBottom: 2 }}>
          {errorMessage(createMutation.error)}
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
          {`Could not load the ingredients. ${errorMessage(loadError ?? new Error(GENERIC_ERROR_MESSAGE))}`}
        </Alert>
      )}

      {!isLoading && !isError && sortedIngredients?.length === 0 && (
        <Typography color="text.secondary">No ingredients recorded yet</Typography>
      )}

      {!isLoading && !isError && sortedIngredients && sortedIngredients.length > 0 && (
        <Table size="small">
          <TableHead>
            <TableRow>
              {COLUMNS.map((column) => (
                <TableCell key={column.key}>
                  <TableSortLabel
                    active={sortColumn === column.key}
                    direction={sortColumn === column.key ? sortOrder : "asc"}
                    onClick={() => handleRequestSort(column.key)}
                  >
                    {column.label}
                  </TableSortLabel>
                </TableCell>
              ))}
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedIngredients.map((ingredient: Ingredient) => (
              <IngredientRow
                key={ingredient.id}
                ingredient={ingredient}
                inShortage={shortageIds.has(ingredient.id)}
                onNavigate={() => navigate(`/warehouse/ingredients/${ingredient.id}`)}
              />
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
