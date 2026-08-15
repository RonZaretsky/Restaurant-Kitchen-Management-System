import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import type { Unit } from "../types/menu";
import type { Ingredient, StockMovement } from "../types/inventory";
import { apiRequest } from "./httpClient";

interface CreateIngredientPayload {
  name: string;
  unit: Unit;
  min_stock_threshold: string;
  current_stock?: string;
}

interface CreateStockMovementPayload {
  movement_type: "purchase" | "waste" | "adjustment";
  quantity: string;
  notes?: string | null;
}

const INGREDIENTS_QUERY_KEY = ["inventory", "ingredients"] as const;
const ingredientQueryKey = (id: number | null) => ["inventory", "ingredients", id] as const;
const movementsQueryKey = (id: number | null) => ["inventory", "ingredients", id, "movements"] as const;

/**
 * Fetches every Ingredient.
 *
 * Kept to this one hook (plus the create mutation added for Story 2.6): an
 * ingredient-detail/stock-levels UI belongs to Epic 4's Story 4.3, this
 * story only needs the list for a recipe-line Ingredient picker and the
 * Ingredients screen's own list.
 *
 * @returns The TanStack Query result for the full Ingredient list.
 */
export function useIngredients(): UseQueryResult<Ingredient[], Error> {
  return useQuery({
    queryKey: INGREDIENTS_QUERY_KEY,
    queryFn: () => apiRequest<Ingredient[]>("/api/inventory/ingredients"),
    // Matches authService's deliberate opt-out. The app-level QueryClient sets no
    // retry, so the default of 3 attempts with backoff would turn a 401/403/404
    // into four requests and a multi-second wait before the error state settles.
    retry: false,
  });
}

/**
 * Creates a new Ingredient (AC4).
 *
 * @returns The TanStack Query mutation for submitting a new Ingredient.
 */
export function useCreateIngredient(): UseMutationResult<Ingredient, Error, CreateIngredientPayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateIngredientPayload) =>
      apiRequest<Ingredient>("/api/inventory/ingredients", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: INGREDIENTS_QUERY_KEY }),
  });
}

/**
 * Fetches one Ingredient by id, for the Ingredient detail screen's stat cards (Story 4.1).
 *
 * @param ingredientId - The id of the Ingredient to fetch, or null while the route
 *   param has not resolved to a usable id yet.
 * @returns The TanStack Query result for this Ingredient.
 */
export function useIngredient(ingredientId: number | null): UseQueryResult<Ingredient, Error> {
  return useQuery({
    queryKey: ingredientQueryKey(ingredientId),
    queryFn: () => apiRequest<Ingredient>(`/api/inventory/ingredients/${ingredientId}`),
    enabled: ingredientId !== null,
    retry: false,
  });
}

/**
 * Fetches every Stock Movement recorded for an Ingredient, newest first (Story 4.1).
 *
 * @param ingredientId - The id of the Ingredient whose history is being read, or null
 *   while the route param has not resolved to a usable id yet.
 * @returns The TanStack Query result for this Ingredient's movement history.
 */
export function useStockMovements(ingredientId: number | null): UseQueryResult<StockMovement[], Error> {
  return useQuery({
    queryKey: movementsQueryKey(ingredientId),
    queryFn: () => apiRequest<StockMovement[]>(`/api/inventory/ingredients/${ingredientId}/movements`),
    enabled: ingredientId !== null,
    retry: false,
  });
}

/**
 * Logs a manual Stock Movement against an Ingredient (AC1/AC2, Story 4.1).
 *
 * Invalidates three keys on settle, not just one: `current_stock` changed, which is cached
 * under the single-ingredient key, the movements-list key, *and* the plain ingredients-list
 * key `IngredientsPage.tsx` already reads, so a Warehouse Manager who logs a movement and
 * then navigates back to the list must not see stale stock. `onSettled`, not `onSuccess`,
 * matching `useEditOrderItem`'s reasoning: a rejected submission (422) means nothing changed
 * here, so the extra invalidation is a harmless no-op, but the pattern stays consistent
 * across this codebase's mutations.
 *
 * @param ingredientId - The id of the Ingredient the movement applies to, or null while the
 *   route param has not resolved to a usable id yet.
 * @returns The TanStack Query mutation for submitting a new Stock Movement.
 */
export function useRecordStockMovement(
  ingredientId: number | null,
): UseMutationResult<StockMovement, Error, CreateStockMovementPayload> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateStockMovementPayload) =>
      apiRequest<StockMovement>(`/api/inventory/ingredients/${ingredientId}/movements`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ingredientQueryKey(ingredientId) });
      void queryClient.invalidateQueries({ queryKey: movementsQueryKey(ingredientId) });
      void queryClient.invalidateQueries({ queryKey: INGREDIENTS_QUERY_KEY });
    },
  });
}
