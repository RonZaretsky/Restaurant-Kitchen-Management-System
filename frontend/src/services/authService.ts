import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import type { CurrentUser, UserRole } from "../types/user";
import { apiRequest } from "./httpClient";

interface LoginPayload {
  username: string;
  password: string;
}

interface LoginResponse {
  role: UserRole;
}

/** The shared cache key for the current-user query, used by both the query and its invalidation. */
export const CURRENT_USER_QUERY_KEY = ["auth", "me"] as const;

/**
 * Submits a login attempt to the backend.
 *
 * @param payload - The username and password to authenticate with.
 * @returns The signed-in User's Role, used to pick the landing surface.
 * @throws ApiError if the credentials are rejected or the backend is
 *   unreachable.
 */
async function login(payload: LoginPayload): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Fetches the authenticated User's own profile.
 *
 * @returns The current User's profile.
 * @throws ApiError with status 401 if there is no valid session cookie.
 */
async function fetchCurrentUser(): Promise<CurrentUser> {
  return apiRequest<CurrentUser>("/api/auth/me");
}

/**
 * Resolves the authenticated User's own profile.
 *
 * A 401 here means "not logged in," not a transient failure, so retries are
 * disabled, retrying would only delay the redirect to Login.
 *
 * @returns The TanStack Query result for the current User's profile.
 */
export function useCurrentUser(): UseQueryResult<CurrentUser, Error> {
  return useQuery({
    queryKey: CURRENT_USER_QUERY_KEY,
    queryFn: fetchCurrentUser,
    retry: false,
  });
}

/**
 * Logs a User in with a username and password.
 *
 * On success, invalidates the current-user query so the shell's cached profile
 * is refetched, and returns that promise so React Query awaits the refetch
 * before running the caller's own `onSuccess`. The caller therefore navigates
 * with the new session already in cache.
 *
 * Returning the promise is for determinism, not correctness. Without it the
 * destination still resolves properly, because refetching a query that errored
 * without ever holding data resets it to `pending` (React Query clears `error`
 * and `status` in `fetchState` when `data === undefined`), so the route guard
 * reads "still loading" and shows its skeleton rather than "rejected session".
 * Awaiting simply removes that skeleton flash and stops the handover depending
 * on a subtle framework detail. Verified both ways in appIntegration.test.tsx.
 *
 * @returns The TanStack Query mutation for submitting a login attempt.
 */
export function useLogin(): UseMutationResult<LoginResponse, Error, LoginPayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: login,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CURRENT_USER_QUERY_KEY }),
  });
}
