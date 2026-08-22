import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";

import type { AIRecipeSuggestion } from "../types/ai";
import { apiRequest } from "./httpClient";

interface GenerateSuggestionPayload {
  direction?: string;
}

/**
 * The shared cache key for the Recipe Suggestion list (Story 6.1).
 *
 * Exported the same way `ALERTS_QUERY_KEY`/`OPEN_ORDERS_QUERY_KEY` already are, so a later
 * live-update subscription (if this domain ever gets one) can invalidate the same key this
 * file's own hooks use.
 */
export const SUGGESTIONS_QUERY_KEY = ["smart-chef", "suggestions"] as const;

/**
 * Fetches every Recipe Suggestion, newest first (AC6).
 *
 * @returns The TanStack Query result for the full suggestion list.
 */
export function useSuggestions(): UseQueryResult<AIRecipeSuggestion[], Error> {
  return useQuery({
    queryKey: SUGGESTIONS_QUERY_KEY,
    queryFn: () => apiRequest<AIRecipeSuggestion[]>("/api/smart-chef/suggestions"),
    retry: false,
  });
}

/**
 * Generates a new Recipe Suggestion from current stock (AC1, AC2).
 *
 * Invalidates the suggestion list on settle, not only on success: a 409 (already generating) or
 * a 502 (generation failed) both mean the client's view of "what's currently happening" may be
 * stale, matching `useAddOrderItem`'s own "invalidate on settle" reasoning.
 *
 * @returns The TanStack Query mutation for generating a suggestion.
 */
export function useGenerateSuggestion(): UseMutationResult<AIRecipeSuggestion, Error, GenerateSuggestionPayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: GenerateSuggestionPayload) =>
      apiRequest<AIRecipeSuggestion>("/api/smart-chef/suggestions", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: SUGGESTIONS_QUERY_KEY }),
  });
}
