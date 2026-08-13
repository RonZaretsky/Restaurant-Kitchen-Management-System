import { useState, type FormEvent } from "react";
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

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [price, setPrice] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [prepTime, setPrepTime] = useState("");
  const [isCreatingCategory, setIsCreatingCategory] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState("");

  const dishesQuery = useDishes();
  const categoriesQuery = useCategories();
  const { data: dishes } = dishesQuery;
  const { data: categories } = categoriesQuery;
  const createDishMutation = useCreateDish();
  const createCategoryMutation = useCreateCategory();

  const isLoading = dishesQuery.isLoading || categoriesQuery.isLoading;
  const isError = dishesQuery.isError || categoriesQuery.isError;
  const firstError = dishesQuery.error ?? categoriesQuery.error ?? new Error(GENERIC_ERROR_MESSAGE);
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
      },
      {
        onSuccess: () => {
          setName("");
          setDescription("");
          setPrice("");
          setCategoryId("");
          setPrepTime("");
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
    if (trimmedName === "") {
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

      {/* Withheld until both queries settle: the Category picker is populated
          from useCategories(), so rendering the form over a failed or in-flight
          categories fetch offers an empty picker and a permanently disabled
          submit with no visible reason. The error Alert below owns that
          explanation instead. */}
      {!isLoading && !isError && (
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
              // the enclosing dish form's implicit submit.
              onKeyDown={(event) => {
                if (event.key === "Enter") {
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
          {`Could not load the menu. ${errorMessage(firstError)}`}
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
