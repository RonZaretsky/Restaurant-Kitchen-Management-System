import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import type { Unit } from "../types/menu";
import type { Ingredient } from "../types/inventory";
import { apiRequest } from "./httpClient";

interface CreateIngredientPayload {
  name: string;
  unit: Unit;
  min_stock_threshold: string;
  current_stock?: string;
}

const INGREDIENTS_QUERY_KEY = ["inventory", "ingredients"] as const;

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
