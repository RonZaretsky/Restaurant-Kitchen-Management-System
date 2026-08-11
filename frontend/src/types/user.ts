/** Mirrors backend/data_models/user.py's UserRole enum values exactly. */
export type UserRole = "admin" | "waiter" | "cook" | "warehouse_manager";

/**
 * Mirrors the JSON shape of backend/data_models/user.py's UserResponse.
 *
 * Field names stay snake_case, matching the API's JSON keys exactly. The
 * backend has no camelCase conversion anywhere, so there is no mapping layer
 * to keep in sync here.
 */
export interface CurrentUser {
  id: number;
  username: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}
