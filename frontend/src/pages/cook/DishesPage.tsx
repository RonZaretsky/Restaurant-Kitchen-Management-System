import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";

import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { useIngredients } from "../../services/inventoryService";
import { ApiError } from "../../services/httpClient";
import { useCategories, useDishes, useRecipeIngredients } from "../../services/menuService";
import type { Dish } from "../../types/menu";
import type { Ingredient } from "../../types/inventory";

/** Shown when a request fails for a reason that carries no user-safe message of its own. */
const GENERIC_ERROR_MESSAGE = "Something went wrong. Try again.";

/**
 * Reads the human-readable message off a failed request.
 *
 * @param error - The error a query failed with.
 * @returns The message to display inline.
 */
function errorMessage(error: Error): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return GENERIC_ERROR_MESSAGE;
}

/**
 * One read-only row for a single Dish: its own fields plus its current
 * Recipe Ingredient lines, joined against `ingredients` for display names.
 *
 * Fetches its own recipe via `useRecipeIngredients(dish.id)` rather than the
 * parent fetching every Dish's recipe up front, mirroring DishRecipeEditor's
 * per-dish fetch shape (a hook cannot be called once per item inside a
 * parent's `.map()`, each item needs its own component instance).
 *
 * A failed recipe fetch is never rendered as "this dish has no recipe",
 * the same distinction DishRecipeEditor draws, so a network blip never
 * misrepresents a dish with a real recipe as one that has none. Likewise a
 * failed Ingredient-list fetch is surfaced explicitly rather than silently
 * falling back to raw ids (AC1 requires names, not ids).
 *
 * @param dish - The Dish this row describes.
 * @param ingredients - Every Ingredient, for resolving a line's display name.
 * @param ingredientsFailed - Whether the Ingredient list failed to load.
 * @returns The read-only row for this Dish.
 */
function DishRow({
  dish,
  ingredients,
  ingredientsFailed,
}: {
  dish: Dish;
  ingredients: Ingredient[] | undefined;
  ingredientsFailed: boolean;
}) {
  const { data: lines, isLoading, isError, error, refetch } = useRecipeIngredients(dish.id);

  const ingredientName = (ingredientId: number) =>
    ingredients?.find((ingredient) => ingredient.id === ingredientId)?.name ?? `#${ingredientId}`;

  return (
    <ListItem component="div" alignItems="flex-start" sx={{ display: "block" }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <ListItemText
          primary={dish.name}
          secondary={
            <>
              {dish.description && <span>{dish.description}</span>}
              <Typography component="span" variant="body2" color="text.secondary" sx={{ display: "block" }}>
                {`$${dish.price} · ${dish.prep_time_minutes ?? "?"} min`}
              </Typography>
            </>
          }
        />
        <Chip
          size="small"
          label={dish.is_available ? "Available" : "Unavailable"}
          color={dish.is_available ? "success" : "default"}
          sx={{ marginLeft: 2 }}
        />
      </Box>

      {isLoading && (
        <Typography variant="body2" color="text.secondary">
          Loading recipe...
        </Typography>
      )}

      {isError && (
        <Alert
          severity="error"
          sx={{ marginTop: 1 }}
          action={
            <Button color="inherit" size="small" onClick={() => refetch()}>
              Retry
            </Button>
          }
        >
          {`Could not load this recipe. ${errorMessage(error)}`}
        </Alert>
      )}

      {!isLoading && !isError && ingredientsFailed && (
        <Alert severity="warning" sx={{ marginTop: 1 }}>
          Could not load ingredient names, showing ingredient ids instead.
        </Alert>
      )}

      {!isLoading && !isError && (
        <Typography variant="body2" color="text.secondary">
          {lines && lines.length > 0
            ? lines.map((line) => ingredientName(line.ingredient_id)).join(", ")
            : "No recipe ingredients yet."}
        </Typography>
      )}
    </ListItem>
  );
}

/**
 * The Dishes (view-only) surface (Story 2.5).
 *
 * Lists every Dish, grouped by Menu Category, with its recipe shown as
 * ingredient names. Strictly read-only (AC2): no create, edit,
 * availability-toggle, or delete control exists anywhere on this page, menu
 * authoring stays Admin-only via Stories 2.2/2.3. Every list here reuses the
 * same TanStack Query hooks the Admin screens already use, none of them set
 * a non-zero staleTime, so this page refetches on every mount exactly like
 * they do, satisfying AC4's "never a stale copy".
 *
 * Loading and error state are combined across all three queries (dishes,
 * categories, ingredients), not just the dish list: a categories or
 * ingredients failure while dishes succeeds must still surface an error
 * rather than silently rendering a blank page or dropping affected dishes.
 *
 * @returns The Dishes page.
 */
export function DishesPage() {
  const dishesQuery = useDishes();
  const categoriesQuery = useCategories();
  const ingredientsQuery = useIngredients();

  const { data: dishes } = dishesQuery;
  const { data: categories } = categoriesQuery;
  const { data: ingredients } = ingredientsQuery;

  const isLoading = dishesQuery.isLoading || categoriesQuery.isLoading || ingredientsQuery.isLoading;
  const isError = dishesQuery.isError || categoriesQuery.isError;
  const firstError = dishesQuery.error ?? categoriesQuery.error ?? new Error(GENERIC_ERROR_MESSAGE);
  const refetchAll = () => {
    void dishesQuery.refetch();
    void categoriesQuery.refetch();
    void ingredientsQuery.refetch();
  };

  // Grouped by each Dish's own category_id, not by iterating the Category list:
  // a Dish whose Category can't be resolved (still loading, or a genuinely
  // missing/deleted one) is still shown, under a `#{id}` fallback heading,
  // rather than silently dropped.
  const categoryName = (categoryId: number) =>
    categories?.find((category) => category.id === categoryId)?.name ?? `#${categoryId}`;
  const categoryIds = Array.from(new Set((dishes ?? []).map((dish) => dish.category_id)));
  const dishesByCategory = categoryIds.map((categoryId) => ({
    categoryId,
    categoryLabel: categoryName(categoryId),
    dishes: (dishes ?? []).filter((dish) => dish.category_id === categoryId),
  }));

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        Dishes
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
          {`Could not load the dish catalog. ${errorMessage(firstError)}`}
        </Alert>
      )}

      {!isLoading && !isError && dishes?.length === 0 && (
        <Typography color="text.secondary">No dishes on the menu yet</Typography>
      )}

      {!isLoading &&
        !isError &&
        dishes &&
        dishes.length > 0 &&
        dishesByCategory.map(({ categoryId, categoryLabel, dishes: dishesInCategory }) => (
          <Box key={categoryId} sx={{ marginBottom: 3 }}>
            <Typography variant="subtitle1" sx={{ marginBottom: 1 }}>
              {categoryLabel}
            </Typography>
            <List>
              {dishesInCategory.map((dish) => (
                <DishRow
                  key={dish.id}
                  dish={dish}
                  ingredients={ingredients}
                  ingredientsFailed={ingredientsQuery.isError}
                />
              ))}
            </List>
          </Box>
        ))}
    </>
  );
}
