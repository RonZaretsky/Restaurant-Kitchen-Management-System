import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import type {
  CreateUserPayload,
  CurrentUser,
  ResetPasswordPayload,
  UpdateUserPayload,
} from "../types/user";
import { apiRequest } from "./httpClient";

const USERS_QUERY_KEY = ["admin", "users"] as const;

/**
 * Fetches every User account.
 *
 * @returns The TanStack Query result for the full User list.
 */
export function useUsers(): UseQueryResult<CurrentUser[], Error> {
  return useQuery({
    queryKey: USERS_QUERY_KEY,
    queryFn: () => apiRequest<CurrentUser[]>("/api/admin/users"),
    // Matches tableService's opt-out: the app-level QueryClient sets no retry,
    // so the default of 3 attempts would turn a 401/403 into four requests.
    retry: false,
  });
}

/**
 * Creates a new User account (AC1).
 *
 * @returns The TanStack Query mutation for submitting a new User.
 */
export function useCreateUser(): UseMutationResult<CurrentUser, Error, CreateUserPayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateUserPayload) =>
      apiRequest<CurrentUser>("/api/admin/users", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY }),
  });
}

/**
 * Edits a User's full name and/or Role (AC3).
 *
 * Invalidates on settle rather than only on success, same reasoning as
 * useUpdateTable: a 409 last-Admin-lockout rejection means this client's
 * cached row is already stale (another Admin's concurrent change is what
 * made this one the last), so the failing path needs the refetch too.
 *
 * @returns The TanStack Query mutation for submitting an edit.
 */
export function useUpdateUser(): UseMutationResult<
  CurrentUser,
  Error,
  { userId: number; payload: UpdateUserPayload }
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, payload }) =>
      apiRequest<CurrentUser>(`/api/admin/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY }),
  });
}

/**
 * Deactivates a User (AC4), rejected with a 409 if they are the last active
 * Admin (AC5).
 *
 * @returns The TanStack Query mutation for deactivating a User by id.
 */
export function useDeactivateUser(): UseMutationResult<CurrentUser, Error, number> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: number) =>
      apiRequest<CurrentUser>(`/api/admin/users/${userId}/deactivate`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY }),
  });
}

/**
 * Reactivates a previously deactivated User (AC7).
 *
 * @returns The TanStack Query mutation for reactivating a User by id.
 */
export function useReactivateUser(): UseMutationResult<CurrentUser, Error, number> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: number) =>
      apiRequest<CurrentUser>(`/api/admin/users/${userId}/reactivate`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY }),
  });
}

/**
 * Sets a new password for a User (AC8).
 *
 * @returns The TanStack Query mutation for resetting a User's password.
 */
export function useResetPassword(): UseMutationResult<
  CurrentUser,
  Error,
  { userId: number; payload: ResetPasswordPayload }
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, payload }) =>
      apiRequest<CurrentUser>(`/api/admin/users/${userId}/reset-password`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY }),
  });
}
