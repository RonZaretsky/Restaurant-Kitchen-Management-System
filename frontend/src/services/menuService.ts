import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import type { Category, Dish, RecipeIngredient, Unit } from "../types/menu";
import { apiRequest } from "./httpClient";

interface AddRecipeIngredientPayload {
  ingredient_id: number;
  quantity: string;
  unit: Unit;
}

interface UpdateRecipeIngredientPayload {
  quantity?: string;
  unit?: Unit;
}

interface UpdateDishAvailabilityPayload {
  is_available: boolean;
}

interface CreateCategoryPayload {
  name: string;
}

interface CreateDishPayload {
  name: string;
  description?: string | null;
  price: string;
  category_id: number;
  prep_time_minutes?: number | null;
}

const CATEGORIES_QUERY_KEY = ["menu", "categories"] as const;
const DISHES_QUERY_KEY = ["menu", "dishes"] as const;

/** The shared cache key for one Dish's recipe, used by the query and every mutation's invalidation. */
function recipeIngredientsQueryKey(dishId: number) {
  return ["menu", "dishes", dishId, "recipe-ingredients"] as const;
}

/**
 * Fetches every Menu Category.
 *
 * @returns The TanStack Query result for the full Category list.
 */
export function useCategories(): UseQueryResult<Category[], Error> {
  return useQuery({
    queryKey: CATEGORIES_QUERY_KEY,
    queryFn: () => apiRequest<Category[]>("/api/menu/categories"),
    retry: false,
  });
}

/**
 * Fetches every Dish.
 *
 * @returns The TanStack Query result for the full Dish list.
 */
export function useDishes(): UseQueryResult<Dish[], Error> {
  return useQuery({
    queryKey: DISHES_QUERY_KEY,
    queryFn: () => apiRequest<Dish[]>("/api/menu/dishes"),
    retry: false,
  });
}

/**
 * Fetches a single Dish's current Recipe Ingredient lines.
 *
 * Always current, never cached across a mutation (every add/update/remove
 * mutation below invalidates this key), matching AC3's "read back is always
 * live" requirement.
 *
 * @param dishId - The Dish whose recipe is being read.
 * @returns The TanStack Query result for that Dish's recipe lines.
 */
export function useRecipeIngredients(dishId: number): UseQueryResult<RecipeIngredient[], Error> {
  return useQuery({
    queryKey: recipeIngredientsQueryKey(dishId),
    queryFn: () => apiRequest<RecipeIngredient[]>(`/api/menu/dishes/${dishId}/recipe-ingredients`),
    retry: false,
  });
}

/**
 * Adds a Recipe Ingredient line to a Dish (AC1).
 *
 * @param dishId - The Dish the line is being added to.
 * @returns The TanStack Query mutation for submitting a new line.
 */
export function useAddRecipeIngredient(
  dishId: number,
): UseMutationResult<RecipeIngredient, Error, AddRecipeIngredientPayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AddRecipeIngredientPayload) =>
      apiRequest<RecipeIngredient>(`/api/menu/dishes/${dishId}/recipe-ingredients`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: recipeIngredientsQueryKey(dishId) }),
  });
}

/**
 * Edits a Recipe Ingredient line's quantity and/or unit.
 *
 * @param dishId - The Dish the line belongs to.
 * @returns The TanStack Query mutation for submitting an edit.
 */
export function useUpdateRecipeIngredient(
  dishId: number,
): UseMutationResult<RecipeIngredient, Error, { ingredientId: number; payload: UpdateRecipeIngredientPayload }> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ ingredientId, payload }) =>
      apiRequest<RecipeIngredient>(`/api/menu/dishes/${dishId}/recipe-ingredients/${ingredientId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: recipeIngredientsQueryKey(dishId) }),
  });
}

/**
 * Removes a Recipe Ingredient line from a Dish (AC2).
 *
 * Only the recipe list is invalidated. The backend never changes
 * `Dish.is_available` on a removal (AD-8 rejects the removal instead), so
 * refetching the Dish list here would be busywork, and its key is a prefix of
 * every open panel's recipe key, so it would refetch those too.
 *
 * @param dishId - The Dish the line belongs to.
 * @returns The TanStack Query mutation for submitting a removal.
 */
export function useRemoveRecipeIngredient(dishId: number): UseMutationResult<void, Error, number> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ingredientId: number) =>
      apiRequest<void>(`/api/menu/dishes/${dishId}/recipe-ingredients/${ingredientId}`, {
        method: "DELETE",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: recipeIngredientsQueryKey(dishId) }),
  });
}

/**
 * Sets a Dish's availability (AC4's "click to enable" path).
 *
 * Reuses Story 2.2's existing `PATCH /api/menu/dishes/{id}` endpoint, no new
 * backend route for this one. The AD-8 zero-recipe rejection is already
 * enforced server-side; this only gives that rejection a caller.
 *
 * @param dishId - The Dish whose availability is changing.
 * @returns The TanStack Query mutation for submitting the change.
 */
export function useUpdateDishAvailability(
  dishId: number,
): UseMutationResult<Dish, Error, UpdateDishAvailabilityPayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: UpdateDishAvailabilityPayload) =>
      apiRequest<Dish>(`/api/menu/dishes/${dishId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DISHES_QUERY_KEY }),
  });
}

/**
 * Creates a new Menu Category (AC2).
 *
 * Appends the created Category to the cached list before invalidating, rather
 * than invalidating alone. Invalidation only *schedules* a refetch, so a caller
 * that selects the new Category immediately (the inline "+ New category" reveal
 * does exactly this) would otherwise hold an id with no matching option until
 * the refetch lands, rendering a blank picker and logging MUI's out-of-range
 * warning. The invalidation still follows, so the server stays the arbiter of
 * the list's real contents.
 *
 * @returns The TanStack Query mutation for submitting a new Category.
 */
export function useCreateCategory(): UseMutationResult<Category, Error, CreateCategoryPayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateCategoryPayload) =>
      apiRequest<Category>("/api/menu/categories", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (category) => {
      queryClient.setQueryData<Category[]>(CATEGORIES_QUERY_KEY, (existing) =>
        existing ? [...existing, category] : [category],
      );
      return queryClient.invalidateQueries({ queryKey: CATEGORIES_QUERY_KEY });
    },
  });
}

/**
 * Creates a new Dish, starting unavailable per AD-8 (AC1).
 *
 * @returns The TanStack Query mutation for submitting a new Dish.
 */
export function useCreateDish(): UseMutationResult<Dish, Error, CreateDishPayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateDishPayload) =>
      apiRequest<Dish>("/api/menu/dishes", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DISHES_QUERY_KEY }),
  });
}
