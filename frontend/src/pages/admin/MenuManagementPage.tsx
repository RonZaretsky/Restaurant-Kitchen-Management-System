import { useState, type FormEvent } from "react";
import { useLocation } from "react-router";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { DishRecipeEditor } from "../../components/menu/DishRecipeEditor";
import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useCategories, useCreateCategory, useCreateDish, useDishes } from "../../services/menuService";

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

/** Shown when the price field holds something that is not a positive number. */
const INVALID_PRICE_MESSAGE = "Enter a price greater than zero";

/** Shown when the prep time field holds something that is not a non-negative whole number. */
const INVALID_PREP_TIME_MESSAGE = "Enter a whole number, zero or greater";

/**
 * The `navigate(path, { state })` payload `RecipeSuggestionsPage.tsx`'s "Confirm into dish"
 * action hands off (Story 6.2, AC1). Ephemeral, one-shot data — deliberately not a URL query
 * param, since it is not meant to be bookmarked or shared.
 */
interface RecipeSuggestionNavigationState {
  prefillName?: string;
  prefillDescription?: string;
  sourceSuggestionId?: number;
}

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
 * Parses a field that must hold a positive decimal price.
 *
 * Deliberately stricter than `Number()`: that coerces `""`/`" "` to 0 and
 * turns anything unparseable into `NaN`, which `JSON.stringify` then
 * serializes as `null`. Returns the trimmed string itself (not a number),
 * matching `Dish.price`'s Decimal-as-string wire convention.
 *
 * @param raw - The raw text from the input.
 * @returns The trimmed price string, or null if it is not a positive number.
 */
function parsePositivePrice(raw: string): string | null {
  const trimmed = raw.trim();
  if (!/^\d+(\.\d+)?$/.test(trimmed)) {
    return null;
  }
  return Number(trimmed) > 0 ? trimmed : null;
}

/**
 * Parses a field that must hold a non-negative whole number.
 *
 * @param raw - The raw text from the input.
 * @returns The parsed integer, or null if the text is not a non-negative whole number.
 */
function parseNonNegativeInteger(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

/**
 * The Menu Management surface (Stories 2.3 and 2.6).
 *
 * Lists every Dish; each row expands into its own recipe editor
 * (DishRecipeEditor), where an Admin adds/edits/removes Recipe Ingredient
 * lines and toggles availability. An always-visible "+ New dish" form above
 * the list creates Dishes (AC1), with an inline "+ New category" reveal on
 * the Category picker for creating a Menu Category without leaving the flow
 * (AC2). No dialog anywhere, matching this codebase's established inline-form
 * convention (`TablesSetupPage`).
 *
 * Loading/error state is combined across both queries (dishes, categories):
 * the create form's Category picker depends on `useCategories()`, so a
 * categories-only failure must still surface an error rather than silently
 * leaving that picker empty with no explanation.
 *
 * @returns The Menu Management page.
 */
export function MenuManagementPage() {
  const [expandedDishId, setExpandedDishId] = useState<number | null>(null);

  // Lazy initializers so a Confirm-into-dish handoff prefills the form only once, on mount —
  // re-rendering (e.g. the Admin clearing the field) must not re-apply navigation state that is
  // still sitting on the same location object.
  const location = useLocation();
  const navigationState = location.state as RecipeSuggestionNavigationState | null;

  const [name, setName] = useState(() => navigationState?.prefillName ?? "");
  const [description, setDescription] = useState(() => navigationState?.prefillDescription ?? "");
  const [price, setPrice] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [prepTime, setPrepTime] = useState("");
  const [isCreatingCategory, setIsCreatingCategory] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState("");
  const [sourceSuggestionId, setSourceSuggestionId] = useState(() => navigationState?.sourceSuggestionId);

  const dishesQuery = useDishes();
  const categoriesQuery = useCategories();
  const { data: dishes } = dishesQuery;
  const { data: categories } = categoriesQuery;
  const createDishMutation = useCreateDish();
  const createCategoryMutation = useCreateCategory();

  const isLoading = dishesQuery.isLoading || categoriesQuery.isLoading;
  const isError = dishesQuery.isError || categoriesQuery.isError;
  const firstError = dishesQuery.error ?? categoriesQuery.error;
  const refetchAll = () => {
    void dishesQuery.refetch();
    void categoriesQuery.refetch();
  };

  const categoryName = (dishCategoryId: number) =>
    categories?.find((category) => category.id === dishCategoryId)?.name ?? `#${dishCategoryId}`;

  const parsedPrice = parsePositivePrice(price);
  const prepTimeTrimmed = prepTime.trim();
  const parsedPrepTime = prepTimeTrimmed === "" ? null : parseNonNegativeInteger(prepTimeTrimmed);
  const isPrepTimeInvalid = prepTimeTrimmed !== "" && parsedPrepTime === null;

  // Gated on the category reveal being closed, not only on the dish fields: the
  // reveal renders inside this same form, so an Enter press in its text field
  // would otherwise submit the dish and silently discard the half-typed
  // category name.
  const canSubmitDish =
    !isCreatingCategory &&
    name.trim() !== "" &&
    parsedPrice !== null &&
    categoryId !== "" &&
    !isPrepTimeInvalid &&
    !createDishMutation.isPending;

  const handleCreateDish = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // Re-checks the full predicate rather than a subset. A disabled button is
    // not authoritative: Enter submits a form regardless, so anything missing
    // here is a request that ships with a blank name or duplicates in flight.
    if (!canSubmitDish || parsedPrice === null) {
      return;
    }
    const trimmedDescription = description.trim();
    createDishMutation.mutate(
      {
        name: name.trim(),
        description: trimmedDescription === "" ? undefined : trimmedDescription,
        price: parsedPrice,
        category_id: Number(categoryId),
        prep_time_minutes: prepTimeTrimmed === "" ? undefined : (parsedPrepTime ?? undefined),
        source_suggestion_id: sourceSuggestionId ?? undefined,
      },
      {
        onSuccess: () => {
          setName("");
          setDescription("");
          setPrice("");
          setCategoryId("");
          setPrepTime("");
          setSourceSuggestionId(undefined);
        },
      },
    );
  };

  const startCreateCategory = () => {
    createCategoryMutation.reset();
    setNewCategoryName("");
    setIsCreatingCategory(true);
  };

  const cancelCreateCategory = () => {
    createCategoryMutation.reset();
    setNewCategoryName("");
    setIsCreatingCategory(false);
  };

  const confirmCreateCategory = () => {
    const trimmedName = newCategoryName.trim();
    // Mirrors the Confirm button's own disabled predicate exactly, isPending
    // included. Enter reaches this without touching the button, so holding it
    // would otherwise fire a second POST while the first is in flight, and
    // whichever resolved first would close the reveal and unmount the other's
    // outcome, hiding a 409 the Admin never gets to see.
    if (trimmedName === "" || createCategoryMutation.isPending) {
      return;
    }
    createCategoryMutation.mutate(
      { name: trimmedName },
      {
        onSuccess: (category) => {
          setCategoryId(String(category.id));
          setNewCategoryName("");
          setIsCreatingCategory(false);
          createCategoryMutation.reset();
        },
      },
    );
  };

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        Menu Management
      </Typography>

      {/* Gated on the Category list being present, which is precisely what the
          form depends on, rather than on the page's combined isLoading/isError.
          Gating on the combined state would take the form away for reasons it
          has nothing to do with: a dishes-only failure (creating a Dish does
          not need the dish list), and any failed background refetch after a
          successful load, which would unmount a half-typed form under the
          Admin. Keyed on the data itself, cached Categories keep the form
          usable through a transient refetch failure. */}
      {categories !== undefined && (
      <Box
        component="form"
        onSubmit={handleCreateDish}
        sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "flex-start", marginBottom: 3 }}
      >
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
        />
        <TextField
          size="small"
          label="Price"
          value={price}
          onChange={(event) => setPrice(event.target.value)}
          error={price !== "" && parsedPrice === null}
          helperText={price !== "" && parsedPrice === null ? INVALID_PRICE_MESSAGE : undefined}
          slotProps={{ htmlInput: { inputMode: "decimal" } }}
        />

        {isCreatingCategory ? (
          <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
            <TextField
              size="small"
              label="New category name"
              value={newCategoryName}
              onChange={(event) => setNewCategoryName(event.target.value)}
              // Enter here confirms the category rather than falling through to
              // the enclosing dish form's implicit submit. isComposing guards
              // the IME case, where Enter commits a candidate rather than
              // meaning "submit", and would otherwise POST partially composed
              // text as the Category name.
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  confirmCreateCategory();
                }
              }}
              error={createCategoryMutation.isError}
              helperText={createCategoryMutation.isError ? errorMessage(createCategoryMutation.error) : undefined}
              slotProps={{ htmlInput: { maxLength: 50 } }}
            />
            <Button
              size="small"
              variant="contained"
              onClick={confirmCreateCategory}
              disabled={newCategoryName.trim() === "" || createCategoryMutation.isPending}
            >
              Confirm
            </Button>
            <Button size="small" onClick={cancelCreateCategory} disabled={createCategoryMutation.isPending}>
              Cancel
            </Button>
          </Box>
        ) : (
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <TextField
              select
              size="small"
              label="Category"
              value={categoryId}
              onChange={(event) => setCategoryId(event.target.value)}
              sx={{ minWidth: 160 }}
            >
              {categories?.map((category) => (
                <MenuItem key={category.id} value={String(category.id)}>
                  {category.name}
                </MenuItem>
              ))}
            </TextField>
            <Button size="small" onClick={startCreateCategory}>
              + New category
            </Button>
          </Box>
        )}

        <TextField
          size="small"
          label="Prep time (minutes)"
          value={prepTime}
          onChange={(event) => setPrepTime(event.target.value)}
          error={isPrepTimeInvalid}
          helperText={isPrepTimeInvalid ? INVALID_PREP_TIME_MESSAGE : undefined}
          slotProps={{ htmlInput: { inputMode: "numeric" } }}
        />

        <Button type="submit" variant="contained" disabled={!canSubmitDish}>
          + New dish
        </Button>

        {/* The reason the submit is dead, as visible text rather than a
            Tooltip, per the standing rule. Without it the open reveal disables
            "+ New dish" with nothing on screen explaining why. */}
        {isCreatingCategory && (
          <Typography variant="caption" color="text.secondary" sx={{ width: "100%" }}>
            Confirm or cancel the new category before adding the dish.
          </Typography>
        )}
      </Box>
      )}

      {createDishMutation.isError && (
        <Alert severity="error" sx={{ marginBottom: 2 }}>
          {errorMessage(createDishMutation.error)}
        </Alert>
      )}

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
          {/* "Try again." rather than errorMessage()'s fallback: this sentence
              already says the load failed, so the generic fallback would render
              "Could not load the menu. Something went wrong. Try again." */}
          {`Could not load the menu. ${firstError instanceof ApiError ? firstError.message : "Try again."}`}
        </Alert>
      )}

      {!isLoading && !isError && dishes?.length === 0 && (
        <Typography color="text.secondary">No dishes yet.</Typography>
      )}

      {!isLoading && !isError && dishes && dishes.length > 0 && (
        <List>
          {dishes.map((dish) => {
            const isExpanded = expandedDishId === dish.id;
            return (
              // component="div" because MUI's ListItem renders an <li> by
              // default; nesting that inside our own <li> would make the
              // parser auto-close the outer one and move the Collapse panel
              // out of the list item it belongs to.
              <ListItem key={dish.id} component="div" sx={{ display: "block" }} disableGutters>
                <ListItem
                  component="div"
                  secondaryAction={
                    <IconButton
                      aria-label={isExpanded ? `Collapse ${dish.name}` : `Expand ${dish.name}`}
                      onClick={() => setExpandedDishId(isExpanded ? null : dish.id)}
                    >
                      {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                    </IconButton>
                  }
                >
                  <ListItemText primary={dish.name} secondary={categoryName(dish.category_id)} />
                  <Chip
                    size="small"
                    label={dish.is_available ? "Available" : "Unavailable"}
                    color={dish.is_available ? "success" : "default"}
                    sx={{ marginRight: 2 }}
                  />
                </ListItem>
                <Collapse in={isExpanded} unmountOnExit>
                  <DishRecipeEditor dish={dish} />
                </Collapse>
              </ListItem>
            );
          })}
        </List>
      )}
    </>
  );
}
