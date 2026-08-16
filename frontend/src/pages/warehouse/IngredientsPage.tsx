import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
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

import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useAlerts, useCreateIngredient, useIngredients } from "../../services/inventoryService";
import type { Ingredient } from "../../types/inventory";
import type { Unit } from "../../types/menu";

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

/** Shown when a threshold/stock field holds something that is not a non-negative number. */
const INVALID_AMOUNT_MESSAGE = "Enter a number, zero or greater";

const UNIT_OPTIONS: Unit[] = ["kg", "liter", "piece"];

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
 * The Ingredients surface (Story 2.6, replacing Story 1.4's placeholder).
 *
 * An always-visible "Add ingredient" form and a dense-row list (Name / Unit /
 * Current stock / Threshold) of every Ingredient (AC4). Story 4.1 added row
 * click-through to the Ingredient detail page, since that is plain navigation
 * and needs no comparison logic (unlike sorting/highlighting), and without it
 * Story 4.1's own detail page (stat cards, log-movement form, movement
 * history) had no discoverable entry point from this screen.
 *
 * Story 4.3 added the shortage row treatment: in-shortage rows (reusing
 * useAlerts()'s already-derived shortage list, Story 4.2, not a second
 * current_stock < min_stock_threshold comparison here) render a
 * WarningAmberIcon plus error-colored text and sort to the top, alphabetical
 * within each group (DESIGN.md's ingredient-row.in-shortage token). Live
 * updates come free from AppShell.tsx's existing global
 * inventory.alerts_changed subscription invalidating the shared
 * ALERTS_QUERY_KEY this page's own useAlerts() call reads from — no second
 * subscription needed here.
 *
 * @returns The Ingredients page.
 */
export function IngredientsPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [unit, setUnit] = useState<Unit | "">("");
  const [threshold, setThreshold] = useState("");
  const [currentStock, setCurrentStock] = useState("");

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

  const sortedIngredients = useMemo(() => {
    if (!ingredients) {
      return undefined;
    }
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
  }, [ingredients, shortageIds]);

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
              <TableCell>Name</TableCell>
              <TableCell>Unit</TableCell>
              <TableCell>Current stock</TableCell>
              <TableCell>Threshold</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedIngredients.map((ingredient: Ingredient) => {
              const inShortage = shortageIds.has(ingredient.id);
              return (
                <TableRow
                  key={ingredient.id}
                  hover
                  onClick={() => navigate(`/warehouse/ingredients/${ingredient.id}`)}
                  sx={{ cursor: "pointer" }}
                >
                  <TableCell sx={inShortage ? { color: "error.main" } : undefined}>
                    {inShortage && (
                      <WarningAmberIcon
                        fontSize="small"
                        color="error"
                        sx={{ verticalAlign: "text-bottom", marginRight: 0.5 }}
                      />
                    )}
                    {ingredient.name}
                  </TableCell>
                  <TableCell sx={inShortage ? { color: "error.main" } : undefined}>{ingredient.unit}</TableCell>
                  <TableCell sx={inShortage ? { color: "error.main" } : undefined}>
                    {ingredient.current_stock}
                  </TableCell>
                  <TableCell sx={inShortage ? { color: "error.main" } : undefined}>
                    {ingredient.min_stock_threshold}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </>
  );
}
