import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import type { Ingredient } from "../types/inventory";
import { apiRequest } from "./httpClient";

/**
 * Fetches every Ingredient.
 *
 * Kept to this one hook: an ingredient-detail/stock-levels UI belongs to
 * Epic 4's Story 4.3, this story only needs the list for a recipe-line
 * Ingredient picker.
 *
 * @returns The TanStack Query result for the full Ingredient list.
 */
export function useIngredients(): UseQueryResult<Ingredient[], Error> {
  return useQuery({
    queryKey: ["inventory", "ingredients"],
    queryFn: () => apiRequest<Ingredient[]>("/api/inventory/ingredients"),
    // Matches authService's deliberate opt-out. The app-level QueryClient sets no
    // retry, so the default of 3 attempts with backoff would turn a 401/403/404
    // into four requests and a multi-second wait before the error state settles.
    retry: false,
  });
}
