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

// Exported, mirrors TABLES_QUERY_KEY/DISHES_QUERY_KEY's cross-file-export
// precedent: both AppShell.tsx's nav badge and AlertsPage.tsx's list independently
// subscribe to inventory.alerts_changed and need to invalidate this same key.
export const ALERTS_QUERY_KEY = ["inventory", "alerts"] as const;

/**
 * Fetches every Ingredient.
 *
 * A plain list read, used for the recipe-line Ingredient picker and the
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
 * Fetches every Ingredient currently in shortage.
 *
 * @param enabled - Whether the query should run at all. AppShell.tsx calls this
 *   unconditionally (hooks cannot be called conditionally) but only a
 *   warehouse_manager has an Alerts nav item to badge, so it passes `false` for
 *   every other Role rather than firing a request that would only 403.
 *   AlertsPage.tsx, reachable only by a warehouse_manager (route guard), omits
 *   this and always fetches.
 * @returns The TanStack Query result for the derived low-stock alert list.
 */
export function useAlerts(enabled = true): UseQueryResult<Ingredient[], Error> {
  return useQuery({
    queryKey: ALERTS_QUERY_KEY,
    queryFn: () => apiRequest<Ingredient[]>("/api/inventory/alerts"),
    enabled,
    retry: false,
  });
}

/**
 * Creates a new Ingredient.
 *
 * Invalidates ALERTS_QUERY_KEY too, not just INGREDIENTS_QUERY_KEY: a new
 * Ingredient can be created with current_stock already below min_stock_threshold, and nothing
 * else would ever refresh the alerts list for it — record_movement's own crossing-triggered
 * broadcast never fires here, since no Stock Movement was involved. Without this,
 * a newly-created in-shortage Ingredient would render with no shortage styling/sort-to-top on
 * IngredientsPage.tsx until some unrelated event happened to invalidate the cache.
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: INGREDIENTS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY });
    },
  });
}

/**
 * Deactivates an Ingredient, blocking new Recipe Ingredient lines and new
 * Stock Movements against it.
 *
 * Invalidates both INGREDIENTS_QUERY_KEY and ALERTS_QUERY_KEY on settle, matching
 * useCreateIngredient's own double-invalidation: a deactivated Ingredient's is_active flag
 * changed (the ingredients list must show it), and while deactivation itself never changes
 * current_stock, invalidating alerts alongside it keeps this mutation consistent with every
 * other one in this file rather than leaving one silent exception.
 *
 * @returns The TanStack Query mutation for deactivating an Ingredient by id.
 */
export function useDeactivateIngredient(): UseMutationResult<Ingredient, Error, number> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ingredientId: number) =>
      apiRequest<Ingredient>(`/api/inventory/ingredients/${ingredientId}/deactivate`, { method: "POST" }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: INGREDIENTS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY });
    },
  });
}

/**
 * Reactivates a previously deactivated Ingredient.
 *
 * @returns The TanStack Query mutation for reactivating an Ingredient by id.
 */
export function useReactivateIngredient(): UseMutationResult<Ingredient, Error, number> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ingredientId: number) =>
      apiRequest<Ingredient>(`/api/inventory/ingredients/${ingredientId}/reactivate`, { method: "POST" }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: INGREDIENTS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY });
    },
  });
}

/**
 * Fetches one Ingredient by id, for the Ingredient detail screen's stat cards.
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
 * Fetches every Stock Movement recorded for an Ingredient, newest first.
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
 * Logs a manual Stock Movement against an Ingredient.
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
