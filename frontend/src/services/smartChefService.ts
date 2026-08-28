import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";

import type { AIChatMessage, AIChatSession, AIRecipeSuggestion } from "../types/ai";
import { apiRequest } from "./httpClient";

interface GenerateSuggestionPayload {
  direction?: string;
  prioritize_waste?: boolean;
}

// Matches backend/clients/llm.py's own _REQUEST_TIMEOUT_SECONDS (45s) with a small margin, so
// the frontend never times out and shows "the server took too long" while the backend's own
// OpenAI call is still legitimately running and about to succeed — a real generation call is
// far slower than an ordinary CRUD request, which is what httpClient's 5s global default assumes
// (manual-test finding: a genuine ~9s generation tripped the 5s default and showed a false
// timeout, even though the request succeeded and the suggestion was persisted).
const GENERATE_SUGGESTION_TIMEOUT_MS = 50_000;

// Same reasoning as GENERATE_SUGGESTION_TIMEOUT_MS above: a chat send also makes a real,
// OpenAI-backed call server-side (LLMClient.send_chat_message, same 45s server-side budget), so
// it must not be left on apiRequest's 5s default either.
const SEND_CHAT_MESSAGE_TIMEOUT_MS = 50_000;

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

/**
 * Dismisses a Recipe Suggestion, retaining it for audit (Story 6.2, AC4).
 *
 * Invalidates the suggestion list on settle, not only on success: a 409 (already dismissed or
 * already confirmed) means the client's view of this suggestion's state is already stale,
 * matching `useGenerateSuggestion`'s own "invalidate on settle" reasoning.
 *
 * @returns The TanStack Query mutation for dismissing a suggestion.
 */
export function useDismissSuggestion(): UseMutationResult<AIRecipeSuggestion, Error, number> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (suggestionId: number) =>
      apiRequest<AIRecipeSuggestion>(`/api/smart-chef/suggestions/${suggestionId}/dismiss`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: SUGGESTIONS_QUERY_KEY }),
  });
}

/**
 * The shared cache key for the Chat Session list (Story 6.3).
 *
 * Exported the same way `SUGGESTIONS_QUERY_KEY` already is, so a later live-update subscription
 * (if this domain ever gets one) can invalidate the same key this file's own hooks use.
 */
export const CHAT_SESSIONS_QUERY_KEY = ["smart-chef", "chat-sessions"] as const;

/**
 * Builds the cache key for one Chat Session's message list.
 *
 * Exported (not inlined per call site) the same way `orderItemsQueryKey`/`orderForTableQueryKey`
 * already are, so a mutation invalidating this key never reconstructs the array by hand.
 *
 * @param sessionId - The Chat Session whose message key is being built.
 * @returns The TanStack Query cache key for that session's messages.
 */
export function chatMessagesQueryKey(sessionId: number) {
  return ["smart-chef", "chat-sessions", sessionId, "messages"] as const;
}

/**
 * Fetches every Chat Session, newest first (AC3, AC6).
 *
 * @returns The TanStack Query result for the full session list.
 */
export function useChatSessions(): UseQueryResult<AIChatSession[], Error> {
  return useQuery({
    queryKey: CHAT_SESSIONS_QUERY_KEY,
    queryFn: () => apiRequest<AIChatSession[]>("/api/smart-chef/chat-sessions"),
    retry: false,
  });
}

/**
 * Fetches a Chat Session's full message history, oldest first (AC1, AC5).
 *
 * `enabled: sessionId !== null` (the established `number | null` + `enabled` gating shape, see
 * `useOrderForTable`'s precedent) — a page cannot know which session is active until the Cook
 * picks one, and must not fire the request with a literal `null` in the URL in the meantime.
 *
 * @param sessionId - The Chat Session whose messages are being fetched, or null if none is
 *   active yet.
 * @returns The TanStack Query result for that session's message list.
 */
export function useChatMessages(sessionId: number | null): UseQueryResult<AIChatMessage[], Error> {
  return useQuery({
    queryKey: chatMessagesQueryKey(sessionId ?? -1),
    queryFn: () => apiRequest<AIChatMessage[]>(`/api/smart-chef/chat-sessions/${sessionId}/messages`),
    enabled: sessionId !== null,
    retry: false,
  });
}

/**
 * Opens a new Chat Session tied to a Dish or a Recipe Suggestion (AC1).
 *
 * Invalidates the session list on settle, matching every other mutation in this file's
 * "invalidate on settle, not just success" convention.
 *
 * @returns The TanStack Query mutation for creating a Chat Session.
 */
export function useCreateChatSession(): UseMutationResult<
  AIChatSession,
  Error,
  { dish_id?: number; suggestion_id?: number }
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { dish_id?: number; suggestion_id?: number }) =>
      apiRequest<AIChatSession>("/api/smart-chef/chat-sessions", { method: "POST", body: JSON.stringify(payload) }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: CHAT_SESSIONS_QUERY_KEY }),
  });
}

/**
 * Sends a message into an existing Chat Session (AC1, AC2, AC4).
 *
 * Uses `SEND_CHAT_MESSAGE_TIMEOUT_MS` (50s) rather than `apiRequest`'s 5s default, matching
 * `useGenerateSuggestion`'s own reasoning: this call is backed by a real OpenAI request
 * server-side, not an ordinary CRUD call.
 *
 * Invalidates that session's message list on settle: a 409 (a reply is already generating) or a
 * 502 (the call failed) both mean the client's view of "what just happened" may be stale,
 * matching every other mutation in this file. `suggestionId` (optional, this batch's #7) is not
 * sent to the backend — the request body still carries only `content`, matching the backend's
 * own `CreateChatMessageRequest` shape — it exists purely so `onSettled` can also invalidate
 * `SUGGESTIONS_QUERY_KEY` when this send targets a Suggestion-tied session, since the backend may
 * have just updated that Suggestion's `generated_recipe` in the same request.
 *
 * @returns The TanStack Query mutation for sending a Chat Message.
 */
export function useSendChatMessage(): UseMutationResult<
  AIChatMessage[],
  Error,
  { sessionId: number; content: string; suggestionId?: number }
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ sessionId, content }: { sessionId: number; content: string; suggestionId?: number }) =>
      apiRequest<AIChatMessage[]>(
        `/api/smart-chef/chat-sessions/${sessionId}/messages`,
        { method: "POST", body: JSON.stringify({ content }) },
        SEND_CHAT_MESSAGE_TIMEOUT_MS,
      ),
    onSettled: (_data, _error, variables) => {
      void queryClient.invalidateQueries({ queryKey: chatMessagesQueryKey(variables.sessionId) });
      if (variables.suggestionId !== undefined) {
        void queryClient.invalidateQueries({ queryKey: SUGGESTIONS_QUERY_KEY });
      }
    },
  });
}
