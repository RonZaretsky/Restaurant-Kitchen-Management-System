import { useEffect, useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";

import { useIngredients } from "../../services/inventoryService";
import {
  useAddRecipeIngredient,
  useRemoveRecipeIngredient,
  useUpdateDishAvailability,
  useUpdateRecipeIngredient,
  useRecipeIngredients,
} from "../../services/menuService";
import { ApiError } from "../../services/httpClient";
import type { Dish, RecipeIngredient, Unit } from "../../types/menu";

/** The units a Recipe Ingredient line can be recorded in, mirrors backend/data_models/recipe.py's Unit enum. */
const UNITS: Unit[] = ["kg", "liter", "piece"];

/**
 * Same wording EmptyRecipeError carries server-side.
 *
 * Duplicated deliberately so the disabled-toggle hint and the 409 an Admin
 * would see if they reached the endpoint anyway never say two different
 * things. `MenuManagementPage.test.tsx` pins the two strings together, so
 * changing the backend wording without changing this one fails the suite
 * rather than drifting silently.
 */
export const EMPTY_RECIPE_MESSAGE = "Cannot mark available, recipe has no ingredients";

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

/**
 * Reads the human-readable message off a failed request.
 *
 * An ApiError already carries the backend's own `detail` string (or a
 * transport message for status 0), so it is shown verbatim rather than
 * replaced with a second, differently-worded copy.
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
 * One editable row of a Dish's recipe.
 *
 * Split into its own component so each row can hold the draft text of its
 * own quantity field. The input is controlled and resynced whenever the
 * server's value changes, so a normalization (`0.3` stored as `0.300`),
 * another Admin's edit, or a rejected change is always reflected back
 * instead of leaving stale text on screen.
 *
 * @param line - The Recipe Ingredient line this row edits.
 * @param ingredientLabel - The Ingredient's display name.
 * @param onQuantityCommit - Called with a new quantity when the field is committed.
 * @param onUnitChange - Called with a new unit when the unit select changes.
 * @param onRemove - Called when the row's delete action is used.
 * @returns The table row for this line.
 */
function RecipeLineRow({
  line,
  ingredientLabel,
  onQuantityCommit,
  onUnitChange,
  onRemove,
}: {
  line: RecipeIngredient;
  ingredientLabel: string;
  onQuantityCommit: (quantity: string) => void;
  onUnitChange: (unit: Unit) => void;
  onRemove: () => void;
}) {
  const [draftQuantity, setDraftQuantity] = useState(line.quantity);
  const [isDirty, setIsDirty] = useState(false);

  // Resync when the server's value changes under us, which a plain defaultValue
  // would never pick up, but never while the field holds uncommitted text: the
  // list refetches on window focus and after any sibling row's save, so
  // resyncing unconditionally would silently replace what the Admin is typing.
  useEffect(() => {
    if (isDirty) {
      return;
    }
    setDraftQuantity(line.quantity);
  }, [line.quantity, isDirty]);

  const commit = () => {
    setIsDirty(false);
    // An empty field is a cleared draft, not a request to store nothing, so
    // put the stored value back rather than leaving the row visibly blank.
    if (draftQuantity === "") {
      setDraftQuantity(line.quantity);
      return;
    }
    if (draftQuantity !== line.quantity) {
      onQuantityCommit(draftQuantity);
    }
  };

  return (
    <TableRow>
      <TableCell>{ingredientLabel}</TableCell>
      <TableCell>
        <TextField
          size="small"
          label={`Quantity of ${ingredientLabel}`}
          value={draftQuantity}
          onChange={(event) => {
            setIsDirty(true);
            setDraftQuantity(event.target.value);
          }}
          onBlur={commit}
          slotProps={{ htmlInput: { inputMode: "decimal" } }}
        />
      </TableCell>
      <TableCell>
        <TextField
          select
          size="small"
          label={`Unit for ${ingredientLabel}`}
          value={line.unit}
          onChange={(event) => onUnitChange(event.target.value as Unit)}
        >
          {UNITS.map((unit) => (
            <MenuItem key={unit} value={unit}>
              {unit}
            </MenuItem>
          ))}
        </TextField>
      </TableCell>
      <TableCell>
        <IconButton aria-label={`Remove ${ingredientLabel}`} size="small" onClick={onRemove}>
          <DeleteIcon fontSize="small" />
        </IconButton>
      </TableCell>
    </TableRow>
  );
}

/**
 * The expand panel for one Dish: its current Recipe Ingredient lines, a form
 * to add another, and the availability toggle.
 *
 * The toggle's disabled state is a pure derived value off the same
 * useRecipeIngredients data the table below already renders, no second
 * fetch and no locally-tracked flag. Adding a dish's first line invalidates
 * that query, the list refetches, the derived boolean flips, and the toggle
 * re-enables with no page reload (AC4).
 *
 * A failed recipe fetch is never rendered as "this dish has no recipe": an
 * errored query and a genuinely empty one are distinguished, because the
 * empty state disables the toggle and would otherwise assert a fact about
 * the data that was never actually loaded.
 *
 * @param dish - The Dish this panel edits the recipe for.
 * @returns The recipe editor for this Dish.
 */
export function DishRecipeEditor({ dish }: { dish: Dish }) {
  const [selectedIngredientId, setSelectedIngredientId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState<Unit>("kg");

  const {
    data: lines,
    isLoading: linesLoading,
    isError: linesFailed,
    error: linesError,
    refetch: refetchLines,
  } = useRecipeIngredients(dish.id);
  const {
    data: ingredients,
    isLoading: ingredientsLoading,
    isError: ingredientsFailed,
  } = useIngredients();
  const addMutation = useAddRecipeIngredient(dish.id);
  const updateMutation = useUpdateRecipeIngredient(dish.id);
  const removeMutation = useRemoveRecipeIngredient(dish.id);
  const availabilityMutation = useUpdateDishAvailability(dish.id);

  const recipeLoaded = !linesLoading && !linesFailed;
  const hasRecipe = recipeLoaded && Boolean(lines && lines.length > 0);
  const isEmptyRecipe = recipeLoaded && !hasRecipe;

  const ingredientName = (ingredientId: number) =>
    ingredients?.find((ingredient) => ingredient.id === ingredientId)?.name ?? `#${ingredientId}`;
  // Only meaningful once the recipe is known. While it is loading or errored,
  // offering every ingredient would let an Admin pick one already on the recipe.
  const ingredientsNotOnRecipe = recipeLoaded
    ? (ingredients ?? []).filter(
        (ingredient) => !lines?.some((line) => line.ingredient_id === ingredient.id),
      )
    : [];

  const handleAdd = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    addMutation.mutate(
      { ingredient_id: Number(selectedIngredientId), quantity, unit },
      {
        onSuccess: () => {
          setSelectedIngredientId("");
          setQuantity("");
        },
      },
    );
  };

  const canSubmitNewLine =
    selectedIngredientId !== "" && quantity !== "" && !addMutation.isPending;

  return (
    <Box sx={{ padding: 2 }}>
      <FormControlLabel
        control={
          <Switch
            checked={dish.is_available}
            disabled={!hasRecipe || availabilityMutation.isPending}
            onChange={(event) => availabilityMutation.mutate({ is_available: event.target.checked })}
          />
        }
        label={dish.is_available ? "Available" : "Unavailable"}
      />
      {isEmptyRecipe && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          {EMPTY_RECIPE_MESSAGE}
        </Typography>
      )}
      {availabilityMutation.isError && (
        <Alert severity="error" sx={{ marginTop: 1 }}>
          {errorMessage(availabilityMutation.error)}
        </Alert>
      )}

      <Typography variant="subtitle2" sx={{ marginTop: 2 }}>
        Recipe (per serving)
      </Typography>

      {linesLoading && (
        <Typography variant="body2" color="text.secondary">
          Loading recipe...
        </Typography>
      )}

      {linesFailed && (
        <Alert
          severity="error"
          sx={{ marginTop: 1 }}
          action={
            <Button color="inherit" size="small" onClick={() => refetchLines()}>
              Retry
            </Button>
          }
        >
          {`Could not load this recipe. ${errorMessage(linesError)}`}
        </Alert>
      )}

      {hasRecipe && (
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Ingredient</TableCell>
              <TableCell>Quantity</TableCell>
              <TableCell>Unit</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {lines!.map((line) => (
              <RecipeLineRow
                key={line.ingredient_id}
                line={line}
                ingredientLabel={ingredientName(line.ingredient_id)}
                onQuantityCommit={(newQuantity) =>
                  updateMutation.mutate({
                    ingredientId: line.ingredient_id,
                    payload: { quantity: newQuantity },
                  })
                }
                onUnitChange={(newUnit) =>
                  updateMutation.mutate({
                    ingredientId: line.ingredient_id,
                    payload: { unit: newUnit },
                  })
                }
                onRemove={() => removeMutation.mutate(line.ingredient_id)}
              />
            ))}
          </TableBody>
        </Table>
      )}

      {isEmptyRecipe && (
        <Typography variant="body2" color="text.secondary">
          No recipe ingredients yet.
        </Typography>
      )}

      {updateMutation.isError && (
        <Alert severity="error" sx={{ marginTop: 1 }}>
          {errorMessage(updateMutation.error)}
        </Alert>
      )}

      {removeMutation.isError && (
        <Alert severity="error" sx={{ marginTop: 1 }}>
          {errorMessage(removeMutation.error)}
        </Alert>
      )}

      <Box
        component="form"
        onSubmit={handleAdd}
        sx={{ display: "flex", flexDirection: "row", gap: 1, marginTop: 2, alignItems: "center" }}
      >
        <TextField
          select
          size="small"
          label="Ingredient"
          value={selectedIngredientId}
          onChange={(event) => setSelectedIngredientId(event.target.value)}
          disabled={ingredientsLoading || ingredientsFailed || !recipeLoaded}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">
            <em>Select ingredient</em>
          </MenuItem>
          {ingredientsNotOnRecipe.map((ingredient) => (
            <MenuItem key={ingredient.id} value={String(ingredient.id)}>
              {ingredient.name}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="Quantity"
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
          slotProps={{ htmlInput: { inputMode: "decimal" } }}
          sx={{ width: 120 }}
        />
        <TextField
          select
          size="small"
          label="Unit"
          value={unit}
          onChange={(event) => setUnit(event.target.value as Unit)}
        >
          {UNITS.map((unitOption) => (
            <MenuItem key={unitOption} value={unitOption}>
              {unitOption}
            </MenuItem>
          ))}
        </TextField>
        <Button type="submit" variant="outlined" disabled={!canSubmitNewLine}>
          + Add recipe ingredient
        </Button>
      </Box>

      {ingredientsFailed && (
        <Alert severity="error" sx={{ marginTop: 1 }}>
          Could not load the ingredient list, so no new line can be added right now.
        </Alert>
      )}

      {addMutation.isError && (
        <Alert severity="error" sx={{ marginTop: 1 }}>
          {errorMessage(addMutation.error)}
        </Alert>
      )}
    </Box>
  );
}
