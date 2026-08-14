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

/** Body of an Admin's request to create a User. Mirrors backend CreateUserRequest. */
export interface CreateUserPayload {
  username: string;
  full_name: string;
  role: UserRole;
  password: string;
}

/**
 * Body of an Admin's request to edit a User's full name and/or Role.
 *
 * At least one field is required — the backend rejects a fully empty body
 * with a 422, mirroring UpdateTableRequest's shape.
 */
export interface UpdateUserPayload {
  full_name?: string;
  role?: UserRole;
}

/** Body of an Admin's password-reset request. The field is new_password, not password. */
export interface ResetPasswordPayload {
  new_password: string;
}
