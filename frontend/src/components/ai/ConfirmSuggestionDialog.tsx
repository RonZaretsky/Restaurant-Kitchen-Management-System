import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";

import { useIngredients } from "../../services/inventoryService";
import { ApiError, apiRequest } from "../../services/httpClient";
import { useCategories, useCreateDish, DISHES_QUERY_KEY } from "../../services/menuService";
import { SUGGESTIONS_QUERY_KEY } from "../../services/smartChefService";
import { useQueryClient } from "@tanstack/react-query";
import type { Unit } from "../../types/menu";
import type { AIRecipeSuggestion } from "../../types/ai";

/** The units a Recipe Ingredient line can be recorded in, mirrors DishRecipeEditor.tsx's own list. */
const UNITS: Unit[] = ["kg", "liter", "piece"];

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

let nextRowKey = 0;

interface DraftIngredientRow {
  key: number;
  sourceLabel: string;
  ingredientId: string;
  quantity: string;
  unit: Unit;
}

/**
 * Extracts the leading decimal amount from the LLM's free-text quantity string (e.g. "1.2 kg" ->
 * "1.2"), best-effort only — the Admin reviews and can correct every prefilled row before
 * submitting, so an unparseable string just leaves the field blank rather than guessing wrong.
 *
 * @param rawQuantity - The suggestion's own free-text quantity for one ingredient.
 * @returns The parsed leading amount, or "" if none is found.
 */
function parseLeadingAmount(rawQuantity: string): string {
  const match = /^\s*(\d+(?:\.\d+)?)/.exec(rawQuantity);
  return match ? match[1] : "";
}

/**
 * Reads the human-readable message off a failed request.
 *
 * @param error - The error a request failed with.
 * @returns The message to display inline.
 */
function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return GENERIC_ERROR_MESSAGE;
}

/**
 * Confirms a Recipe Suggestion directly into a live Dish, in one dialog (Story 6.2, revised per
 * manual-test feedback: the original design handed off to the Menu Management create form via
 * navigation state, requiring the Admin to separately re-add every Recipe Ingredient line by
 * hand afterward; this dialog creates the Dish AND its Recipe Ingredient lines in the same flow).
 *
 * Each suggested ingredient is prefilled with a best-effort match against the real Ingredient
 * list (case-insensitive name match) and a best-effort parsed quantity, but every field stays
 * editable: the AI's `generated_recipe.ingredients` are free-text name/quantity pairs, not
 * validated Ingredient ids or units, so an unmatched or unparseable row is left blank for the
 * Admin to fill in rather than silently guessing.
 *
 * Composes the two existing endpoints (`POST /api/menu/dishes`, then
 * `POST /api/menu/dishes/{id}/recipe-ingredients` per row) rather than adding a new backend
 * action — `MenuService.create_dish` remains the only Dish-creation path (AC2), and
 * `add_recipe_ingredient` remains the only way a Recipe Ingredient line is ever added.
 *
 * @param suggestion - The Recipe Suggestion being confirmed.
 * @param onClose - Called when the dialog is dismissed, confirmed or cancelled.
 * @returns The confirm dialog.
 */
export function ConfirmSuggestionDialog({
  suggestion,
  onClose,
}: {
  suggestion: AIRecipeSuggestion;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const categoriesQuery = useCategories();
  const ingredientsQuery = useIngredients();
  const createDishMutation = useCreateDish();

  const [name, setName] = useState(suggestion.generated_recipe.name);
  const [description, setDescription] = useState(suggestion.generated_recipe.plating);
  const [price, setPrice] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [prepTime, setPrepTime] = useState("");
  const [rows, setRows] = useState<DraftIngredientRow[]>(() =>
    suggestion.generated_recipe.ingredients.map((ingredient) => ({
      key: nextRowKey++,
      sourceLabel: `${ingredient.name}, ${ingredient.quantity}`,
      ingredientId: "",
      quantity: parseLeadingAmount(ingredient.quantity),
      unit: "kg" as Unit,
    })),
  );
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Best-effort ingredient matching runs once real Ingredient data is available, not on every
  // render — re-running it after the Admin has already started editing rows would silently
  // overwrite their picks.
  const [matched, setMatched] = useState(false);
  const ingredients = ingredientsQuery.data;
  if (ingredients && !matched) {
    setMatched(true);
    setRows((currentRows) =>
      currentRows.map((row) => {
        const suggested = suggestion.generated_recipe.ingredients.find(
          (ingredient) => row.sourceLabel === `${ingredient.name}, ${ingredient.quantity}`,
        );
        const realIngredient = suggested
          ? ingredients.find((candidate) => candidate.name.toLowerCase() === suggested.name.toLowerCase())
          : undefined;
        return realIngredient
          ? { ...row, ingredientId: String(realIngredient.id), unit: realIngredient.unit }
          : row;
      }),
    );
  }

  const parsedPrice = /^\d+(\.\d+)?$/.test(price.trim()) && Number(price.trim()) > 0 ? price.trim() : null;
  const trimmedPrepTime = prepTime.trim();
  const isPrepTimeValid = trimmedPrepTime === "" || /^\d+$/.test(trimmedPrepTime);

  const activeRows = rows.filter((row) => row.ingredientId !== "" || row.quantity !== "");
  const rowsValid = activeRows.every((row) => row.ingredientId !== "" && row.quantity !== "");

  const canSubmit =
    name.trim() !== "" &&
    parsedPrice !== null &&
    categoryId !== "" &&
    isPrepTimeValid &&
    rowsValid &&
    !submitting;

  const updateRow = (key: number, patch: Partial<DraftIngredientRow>) =>
    setRows((currentRows) => currentRows.map((row) => (row.key === key ? { ...row, ...patch } : row)));

  const removeRow = (key: number) => setRows((currentRows) => currentRows.filter((row) => row.key !== key));

  const ingredientName = (ingredientId: string) =>
    ingredients?.find((candidate) => String(candidate.id) === ingredientId)?.name ?? "";

  const handleConfirm = async () => {
    if (!canSubmit || parsedPrice === null) {
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const dish = await createDishMutation.mutateAsync({
        name: name.trim(),
        description: description.trim() === "" ? undefined : description.trim(),
        price: parsedPrice,
        category_id: Number(categoryId),
        prep_time_minutes: trimmedPrepTime === "" ? undefined : Number(trimmedPrepTime),
        source_suggestion_id: suggestion.id,
      });

      const failedIngredients: string[] = [];
      for (const row of activeRows) {
        try {
          await apiRequest(`/api/menu/dishes/${dish.id}/recipe-ingredients`, {
            method: "POST",
            body: JSON.stringify({ ingredient_id: Number(row.ingredientId), quantity: row.quantity, unit: row.unit }),
          });
        } catch (error) {
          failedIngredients.push(`${ingredientName(row.ingredientId)}: ${errorMessage(error)}`);
        }
      }

      // Marks the Dish available once it has at least one Recipe Ingredient line, matching
      // AD-8's own rule (a Dish stays unavailable with zero lines) — unlike an ordinary new Dish,
      // this one is being created with its recipe already attached in the same flow, so there is
      // no separate "come back later and flip availability" step for the Admin to remember.
      let availabilityError: string | null = null;
      if (activeRows.length > failedIngredients.length) {
        try {
          await apiRequest(`/api/menu/dishes/${dish.id}`, {
            method: "PATCH",
            body: JSON.stringify({ is_available: true }),
          });
        } catch (error) {
          availabilityError = errorMessage(error);
        }
      }

      await queryClient.invalidateQueries({ queryKey: SUGGESTIONS_QUERY_KEY });
      await queryClient.invalidateQueries({ queryKey: DISHES_QUERY_KEY });

      if (failedIngredients.length > 0 || availabilityError) {
        // The Dish itself was created successfully (and is now confirmed), so this is not a
        // failed confirmation — only some ingredient lines (and/or the availability flip) need a
        // manual follow-up in Menu Management's existing recipe editor, same as any rejected
        // Recipe Ingredient edit today.
        const parts = [
          ...(failedIngredients.length > 0
            ? [`these ingredient lines were rejected and were not added: ${failedIngredients.join("; ")}`]
            : []),
          ...(availabilityError ? [`could not mark it available (${availabilityError})`] : []),
        ];
        setSubmitError(`Dish created, but ${parts.join("; and ")}. Finish this from Menu Management.`);
        setSubmitting(false);
        return;
      }
      onClose();
    } catch (error) {
      setSubmitError(errorMessage(error));
      setSubmitting(false);
    }
  };

  const dataLoading = categoriesQuery.isLoading || ingredientsQuery.isLoading;
  const dataFailed = categoriesQuery.isError || ingredientsQuery.isError;

  return (
    <Dialog open onClose={submitting ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Confirm into Dish</DialogTitle>
      <DialogContent>
        {dataFailed && (
          <Alert severity="error" sx={{ marginBottom: 2 }}>
            Could not load categories/ingredients, so this suggestion cannot be confirmed right now.
          </Alert>
        )}

        {!dataLoading && !dataFailed && (
          <Stack spacing={2} sx={{ marginTop: 1 }}>
            <TextField
              size="small"
              label="Dish name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              slotProps={{ htmlInput: { maxLength: 100 } }}
            />
            <TextField
              size="small"
              label="Description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              multiline
            />
            <Stack direction="row" spacing={2}>
              <TextField
                select
                size="small"
                label="Category"
                value={categoryId}
                onChange={(event) => setCategoryId(event.target.value)}
                sx={{ minWidth: 160 }}
              >
                {categoriesQuery.data?.map((category) => (
                  <MenuItem key={category.id} value={String(category.id)}>
                    {category.name}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                size="small"
                label="Price"
                value={price}
                onChange={(event) => setPrice(event.target.value)}
                error={price !== "" && parsedPrice === null}
                slotProps={{ htmlInput: { inputMode: "decimal" } }}
              />
              <TextField
                size="small"
                label="Prep time (minutes)"
                value={prepTime}
                onChange={(event) => setPrepTime(event.target.value)}
                error={!isPrepTimeValid}
                slotProps={{ htmlInput: { inputMode: "numeric" } }}
              />
            </Stack>

            <Typography variant="subtitle2">Recipe ingredients</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Suggested</TableCell>
                  <TableCell>Ingredient</TableCell>
                  <TableCell>Quantity</TableCell>
                  <TableCell>Unit</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.key}>
                    <TableCell>{row.sourceLabel}</TableCell>
                    <TableCell>
                      <TextField
                        select
                        size="small"
                        value={row.ingredientId}
                        onChange={(event) => updateRow(row.key, { ingredientId: event.target.value })}
                        sx={{ minWidth: 140 }}
                      >
                        <MenuItem value="">
                          <em>Select</em>
                        </MenuItem>
                        {ingredients?.map((ingredient) => (
                          <MenuItem key={ingredient.id} value={String(ingredient.id)}>
                            {ingredient.name}
                          </MenuItem>
                        ))}
                      </TextField>
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        value={row.quantity}
                        onChange={(event) => updateRow(row.key, { quantity: event.target.value })}
                        slotProps={{ htmlInput: { inputMode: "decimal" } }}
                        sx={{ width: 90 }}
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        select
                        size="small"
                        value={row.unit}
                        onChange={(event) => updateRow(row.key, { unit: event.target.value as Unit })}
                      >
                        {UNITS.map((unit) => (
                          <MenuItem key={unit} value={unit}>
                            {unit}
                          </MenuItem>
                        ))}
                      </TextField>
                    </TableCell>
                    <TableCell>
                      <IconButton aria-label={`Remove ${row.sourceLabel}`} size="small" onClick={() => removeRow(row.key)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {submitError && <Alert severity="error">{submitError}</Alert>}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button variant="contained" onClick={handleConfirm} disabled={!canSubmit || dataLoading || dataFailed}>
          Confirm
        </Button>
      </DialogActions>
    </Dialog>
  );
}
