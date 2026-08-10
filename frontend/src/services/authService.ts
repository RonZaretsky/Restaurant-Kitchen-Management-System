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

async function login(payload: LoginPayload): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

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
 * On success, invalidates the current-user query so the shell's cached
 * profile is refetched. The caller is responsible for navigating to the
 * Role's home surface using the `role` already present in the mutation's
 * result, without waiting for that refetch.
 *
 * @returns The TanStack Query mutation for submitting a login attempt.
 */
export function useLogin(): UseMutationResult<LoginResponse, Error, LoginPayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: login,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CURRENT_USER_QUERY_KEY });
    },
  });
}
