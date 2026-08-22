import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";

import type { AIRecipeSuggestion } from "../types/ai";
import { apiRequest } from "./httpClient";

interface GenerateSuggestionPayload {
  direction?: string;
}

// Matches backend/clients/llm.py's own _REQUEST_TIMEOUT_SECONDS (45s) with a small margin, so
// the frontend never times out and shows "the server took too long" while the backend's own
// OpenAI call is still legitimately running and about to succeed — a real generation call is
// far slower than an ordinary CRUD request, which is what httpClient's 5s global default assumes
// (manual-test finding: a genuine ~9s generation tripped the 5s default and showed a false
// timeout, even though the request succeeded and the suggestion was persisted).
const GENERATE_SUGGESTION_TIMEOUT_MS = 50_000;

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
 * Uses `GENERATE_SUGGESTION_TIMEOUT_MS` (50s) rather than `apiRequest`'s 5s default — a real
 * OpenAI call routinely takes several seconds and legitimately up to `LLMClient`'s own
 * server-side 45s budget, far longer than any ordinary CRUD request in this app.
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
      apiRequest<AIRecipeSuggestion>(
        "/api/smart-chef/suggestions",
        { method: "POST", body: JSON.stringify(payload) },
        GENERATE_SUGGESTION_TIMEOUT_MS,
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: SUGGESTIONS_QUERY_KEY }),
  });
}
