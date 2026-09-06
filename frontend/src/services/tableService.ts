import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import type { Table } from "../types/table";
import { apiRequest } from "./httpClient";

interface CreateTablePayload {
  table_number: number;
  capacity: number;
}

interface UpdateTablePayload {
  table_number?: number;
  capacity?: number;
}

/** The shared cache key for the Table list, reused by orderService.ts's useOpenTable(). */
export const TABLES_QUERY_KEY = ["tables"] as const;

/**
 * Fetches every Restaurant Table.
 *
 * @returns The TanStack Query result for the full Table list.
 */
export function useTables(): UseQueryResult<Table[], Error> {
  return useQuery({
    queryKey: TABLES_QUERY_KEY,
    queryFn: () => apiRequest<Table[]>("/api/tables"),
    // Matches authService's deliberate opt-out: the app-level QueryClient sets no retry, so the
    // default of 3 attempts would turn a 401/403 into four requests and a
    // multi-second wait before the error state settles.
    retry: false,
  });
}

/**
 * Creates a new Restaurant Table, starting available.
 *
 * @returns The TanStack Query mutation for submitting a new Table.
 */
export function useCreateTable(): UseMutationResult<Table, Error, CreateTablePayload> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateTablePayload) =>
      apiRequest<Table>("/api/tables", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TABLES_QUERY_KEY }),
  });
}

/**
 * Edits a Table's number and/or capacity, only while it is available.
 *
 * Invalidates on settle rather than only on success. A rejected save is the
 * case that most needs a refresh: a 409 "table in use" means this client's copy
 * of the row is already stale, and without a refetch the row keeps rendering an
 * `available` Chip and an enabled Save button next to the error, so the Admin
 * can retry forever against state that will never accept them.
 *
 * @returns The TanStack Query mutation for submitting an edit.
 */
export function useUpdateTable(): UseMutationResult<
  Table,
  Error,
  { tableId: number; payload: UpdateTablePayload }
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ tableId, payload }) =>
      apiRequest<Table>(`/api/tables/${tableId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TABLES_QUERY_KEY }),
  });
}
