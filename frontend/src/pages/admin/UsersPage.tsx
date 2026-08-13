import { useEffect, useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select, { type SelectChangeEvent } from "@mui/material/Select";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { useCurrentUser } from "../../services/authService";
import { ApiError } from "../../services/httpClient";
import {
  useCreateUser,
  useDeactivateUser,
  useReactivateUser,
  useResetPassword,
  useUpdateUser,
  useUsers,
} from "../../services/userService";
import type { CurrentUser, UserRole } from "../../types/user";

/** Backend bounds, from data_models/user.py's CreateUserRequest/UpdateUserRequest. */
const MAX_USERNAME_LENGTH = 50;
const MAX_FULL_NAME_LENGTH = 100;

/**
 * Every Role a User can hold, with the Chip colour the UX mock assigns it.
 *
 * `key-users.html` gives each Role a distinct treatment (admin purple, waiter
 * blue, cook orange, warehouse teal); MUI's palette slots are the nearest
 * equivalent that still respects the theme in both light and dark mode.
 */
const ROLE_OPTIONS: {
  value: UserRole;
  label: string;
  color: "secondary" | "primary" | "warning" | "info";
}[] = [
  { value: "admin", label: "Admin", color: "secondary" },
  { value: "waiter", label: "Waiter", color: "primary" },
  { value: "cook", label: "Cook", color: "warning" },
  { value: "warehouse_manager", label: "Warehouse Manager", color: "info" },
];

/**
 * Looks up a Role's display metadata.
 *
 * @param role - The Role to describe.
 * @returns The matching option, or a neutral fallback if the backend ever
 *   grows a Role this build does not know about.
 */
function roleOption(role: UserRole) {
  return ROLE_OPTIONS.find((option) => option.value === role);
}

/**
 * Reads the human-readable message off a failed request.
 *
 * @param error - The error a query or mutation failed with.
 * @returns The message to display inline.
 */
function errorMessage(error: Error): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Something went wrong. Try again.";
}

interface UserListRowProps {
  user: CurrentUser;
  /** The signed-in Admin's own id, or undefined while their profile is unknown. */
  currentUserId: number | undefined;
}

/**
 * One row of the Users list, owning its own edit, password-reset and
 * deactivate-confirmation state.
 *
 * Mirrors TablesSetupPage's TableListRow: editable fields resync from the
 * server's value only while this row is not mid-edit, so a background
 * refetch never clobbers text the Admin is still typing.
 *
 * @param props - The User this row displays and the signed-in Admin's id.
 * @returns The table row.
 */
function UserListRow({ user, currentUserId }: UserListRowProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draftFullName, setDraftFullName] = useState(user.full_name);
  const [draftRole, setDraftRole] = useState<UserRole>(user.role);
  const [isResettingPassword, setIsResettingPassword] = useState(false);
  const [draftPassword, setDraftPassword] = useState("");
  const [isConfirmingDeactivate, setIsConfirmingDeactivate] = useState(false);

  const updateMutation = useUpdateUser();
  const deactivateMutation = useDeactivateUser();
  const reactivateMutation = useReactivateUser();
  const resetPasswordMutation = useResetPassword();

  useEffect(() => {
    if (isEditing) {
      return;
    }
    setDraftFullName(user.full_name);
    setDraftRole(user.role);
  }, [user.full_name, user.role, isEditing]);

  const trimmedName = draftFullName.trim();
  const isNameEmpty = trimmedName.length === 0;
  const isNameTooLong = trimmedName.length > MAX_FULL_NAME_LENGTH;
  const isNameValid = !isNameEmpty && !isNameTooLong;
  const nameHelperText = isNameEmpty
    ? "Full name is required"
    : isNameTooLong
      ? `Full name must be ${MAX_FULL_NAME_LENGTH} characters or fewer`
      : undefined;

  // Deliberately NOT gated on "has anything changed". Diffing the draft against
  // the cached row is forbidden (project-context: "Never diff a form against
  // cached data to decide what to send"): if another Admin has already changed
  // this value, the cache is stale, and typing the value you actually want
  // produces either a disabled Save or a payload that reverts their change.
  const canSave = isNameValid && !updateMutation.isPending;

  /**
   * Clears every mutation's error state on this row.
   *
   * All four are reset together, not just the one whose panel is opening: the
   * row renders a single error slot, so an error left set on a mutation the
   * Admin has moved on from would outlive the action that caused it and
   * reappear attached to an unrelated, successful one.
   */
  const resetRowErrors = () => {
    updateMutation.reset();
    deactivateMutation.reset();
    reactivateMutation.reset();
    resetPasswordMutation.reset();
  };

  const startEdit = () => {
    resetRowErrors();
    setIsEditing(true);
  };

  const cancelEdit = () => {
    resetRowErrors();
    setDraftFullName(user.full_name);
    setDraftRole(user.role);
    setIsEditing(false);
  };

  const save = () => {
    if (!canSave) {
      return;
    }
    // Both fields are always sent, never diffed against the cached row. The
    // backend already skips a no-op edit without committing or logging, so
    // sending both costs nothing and is the only version that cannot silently
    // revert a concurrent change to the field this Admin did not touch.
    updateMutation.mutate(
      { userId: user.id, payload: { full_name: trimmedName, role: draftRole } },
      { onSuccess: () => setIsEditing(false) },
    );
  };

  const startResetPassword = () => {
    resetRowErrors();
    setDraftPassword("");
    setIsResettingPassword(true);
  };

  const cancelResetPassword = () => {
    resetRowErrors();
    setDraftPassword("");
    setIsResettingPassword(false);
  };

  const saveResetPassword = () => {
    if (draftPassword.length === 0 || resetPasswordMutation.isPending) {
      return;
    }
    resetPasswordMutation.mutate(
      { userId: user.id, payload: { new_password: draftPassword } },
      {
        onSuccess: () => {
          setDraftPassword("");
          setIsResettingPassword(false);
        },
      },
    );
  };

  const confirmDeactivate = () => {
    deactivateMutation.mutate(user.id, {
      onSuccess: () => setIsConfirmingDeactivate(false),
    });
  };

  // Fails closed: while the signed-in Admin's identity is unknown, no row is
  // treated as "not me", so Deactivate is withheld rather than offered on a row
  // that might be their own. RequireAuth guarantees the profile is loaded
  // before this page mounts, but this component's contract permits undefined
  // and the safe reading of "unknown" is "could be me".
  const isIdentityKnown = currentUserId !== undefined;
  const isSelf = user.id === currentUserId;
  const canDeactivate = isIdentityKnown && !isSelf;

  // The most recently submitted failure wins. A fixed `??` precedence chain
  // would keep showing an earlier mutation's error instead of the one the
  // Admin just triggered, telling them the wrong reason their action failed.
  const activeError = [updateMutation, deactivateMutation, reactivateMutation, resetPasswordMutation]
    .filter((mutation) => mutation.isError)
    .sort((a, b) => b.submittedAt - a.submittedAt)[0]?.error;

  const role = roleOption(user.role);

  return (
    <>
      <TableRow>
        <TableCell sx={{ fontFamily: "monospace" }}>{user.username}</TableCell>
        <TableCell>
          {isEditing ? (
            <TextField
              size="small"
              label={`Full name for ${user.username}`}
              value={draftFullName}
              onChange={(event) => setDraftFullName(event.target.value)}
              error={!isNameValid}
              helperText={nameHelperText}
            />
          ) : (
            user.full_name
          )}
        </TableCell>
        <TableCell>
          {isEditing ? (
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel id={`role-label-${user.id}`}>{`Role for ${user.username}`}</InputLabel>
              <Select
                labelId={`role-label-${user.id}`}
                label={`Role for ${user.username}`}
                value={draftRole}
                onChange={(event: SelectChangeEvent) => setDraftRole(event.target.value as UserRole)}
              >
                {ROLE_OPTIONS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          ) : (
            <Chip size="small" label={role?.label ?? user.role} color={role?.color ?? "default"} />
          )}
        </TableCell>
        <TableCell>
          <Chip
            size="small"
            label={user.is_active ? "Active" : "Inactive"}
            color={user.is_active ? "success" : "default"}
          />
        </TableCell>
        <TableCell align="right">
          {isEditing ? (
            <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end" }}>
              <Button size="small" variant="contained" onClick={save} disabled={!canSave}>
                Save
              </Button>
              <Button size="small" onClick={cancelEdit} disabled={updateMutation.isPending}>
                Cancel
              </Button>
            </Box>
          ) : isResettingPassword ? (
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", justifyContent: "flex-end" }}>
              <TextField
                size="small"
                type="password"
                label={`New password for ${user.username}`}
                value={draftPassword}
                onChange={(event) => setDraftPassword(event.target.value)}
                slotProps={{ htmlInput: { autoComplete: "new-password" } }}
              />
              <Button
                size="small"
                variant="contained"
                onClick={saveResetPassword}
                disabled={draftPassword.length === 0 || resetPasswordMutation.isPending}
              >
                Save
              </Button>
              <Button size="small" onClick={cancelResetPassword} disabled={resetPasswordMutation.isPending}>
                Cancel
              </Button>
            </Box>
          ) : isConfirmingDeactivate ? (
            // An in-row confirm rather than a modal: deactivation blocks a
            // staff member's login mid-shift, and naming them here makes a
            // misclick on the wrong row visible before it lands. Uses the same
            // in-place reveal Edit and Reset password already use, so no
            // dialog pattern is introduced.
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", justifyContent: "flex-end" }}>
              <Typography variant="caption">{`Deactivate ${user.full_name}?`}</Typography>
              <Button
                size="small"
                variant="contained"
                color="error"
                onClick={confirmDeactivate}
                disabled={deactivateMutation.isPending}
              >
                Confirm
              </Button>
              <Button
                size="small"
                onClick={() => setIsConfirmingDeactivate(false)}
                disabled={deactivateMutation.isPending}
              >
                Cancel
              </Button>
            </Box>
          ) : (
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", justifyContent: "flex-end" }}>
              <Button size="small" onClick={startEdit}>
                Edit
              </Button>
              <Button size="small" onClick={startResetPassword}>
                Reset password
              </Button>
              {user.is_active && isSelf && (
                <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center" }}>
                  This is you
                </Typography>
              )}
              {user.is_active && canDeactivate && (
                <Button
                  size="small"
                  color="error"
                  onClick={() => {
                    resetRowErrors();
                    setIsConfirmingDeactivate(true);
                  }}
                  disabled={deactivateMutation.isPending}
                >
                  Deactivate
                </Button>
              )}
              {!user.is_active && (
                <Button
                  size="small"
                  onClick={() => {
                    resetRowErrors();
                    reactivateMutation.mutate(user.id);
                  }}
                  disabled={reactivateMutation.isPending}
                >
                  Reactivate
                </Button>
              )}
            </Box>
          )}
        </TableCell>
      </TableRow>
      {activeError && (
        <TableRow>
          <TableCell colSpan={5}>
            <Alert severity="error">{errorMessage(activeError)}</Alert>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

/**
 * The Users setup surface (Story 1.6).
 *
 * A "+ New user" form and a dense-row list (UX-DR8) of every User account,
 * each row supporting inline edit, deactivate (behind an in-row confirm),
 * reactivate, and password reset. The signed-in Admin's own row shows
 * "This is you" in place of Deactivate (AC6), so self-deactivation is never
 * reachable from this screen. The last-active-Admin lockout (AD-15) is
 * enforced server-side; this page only surfaces its 409 inline.
 *
 * @returns The Users page.
 */
export function UsersPage() {
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<UserRole>("waiter");
  const [password, setPassword] = useState("");

  const { data: users, isLoading, isError, error, refetch } = useUsers();
  const { data: currentUser } = useCurrentUser();
  const createMutation = useCreateUser();

  const trimmedUsername = username.trim();
  const trimmedFullName = fullName.trim();
  const isUsernameTooLong = trimmedUsername.length > MAX_USERNAME_LENGTH;
  const isFullNameTooLong = trimmedFullName.length > MAX_FULL_NAME_LENGTH;

  const canSubmit =
    trimmedUsername.length > 0 &&
    !isUsernameTooLong &&
    trimmedFullName.length > 0 &&
    !isFullNameTooLong &&
    password.length > 0 &&
    !createMutation.isPending;

  const handleCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    createMutation.mutate(
      { username: trimmedUsername, full_name: trimmedFullName, role, password },
      {
        onSuccess: () => {
          setUsername("");
          setFullName("");
          setRole("waiter");
          setPassword("");
        },
      },
    );
  };

  const activeCount = users?.filter((user) => user.is_active).length ?? 0;

  // A failed refetch keeps the previously loaded data in cache. Rendering the
  // error *alongside* the table, rather than instead of it, is what stops an
  // alt-tab blip from unmounting every open editor and any typed password.
  const hasUsers = users !== undefined;

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        Users
      </Typography>
      {hasUsers && !isError && (
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {`${users.length} staff ${users.length === 1 ? "account" : "accounts"} · ${activeCount} active`}
        </Typography>
      )}

      <Box
        component="form"
        onSubmit={handleCreate}
        sx={{ display: "flex", flexDirection: "row", gap: 1, alignItems: "flex-start", flexWrap: "wrap", marginBottom: 3 }}
      >
        <TextField
          size="small"
          label="Username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          error={isUsernameTooLong}
          helperText={isUsernameTooLong ? `Username must be ${MAX_USERNAME_LENGTH} characters or fewer` : undefined}
          slotProps={{ htmlInput: { autoComplete: "off" } }}
        />
        <TextField
          size="small"
          label="Full name"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          error={isFullNameTooLong}
          helperText={isFullNameTooLong ? `Full name must be ${MAX_FULL_NAME_LENGTH} characters or fewer` : undefined}
          slotProps={{ htmlInput: { autoComplete: "off" } }}
        />
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="new-user-role-label">Role</InputLabel>
          <Select
            labelId="new-user-role-label"
            label="Role"
            value={role}
            onChange={(event: SelectChangeEvent) => setRole(event.target.value as UserRole)}
          >
            {ROLE_OPTIONS.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {option.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <TextField
          size="small"
          type="password"
          label="Initial password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          slotProps={{ htmlInput: { autoComplete: "new-password" } }}
        />
        <Button type="submit" variant="contained" disabled={!canSubmit}>
          + New user
        </Button>
      </Box>

      {createMutation.isError && (
        <Alert severity="error" sx={{ marginBottom: 2 }}>
          {errorMessage(createMutation.error)}
        </Alert>
      )}

      {isLoading && <RowsSkeleton count={5} />}

      {isError && (
        <Alert
          severity="error"
          sx={{ marginBottom: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => refetch()}>
              Retry
            </Button>
          }
        >
          {`Could not load the users. ${errorMessage(error)}`}
        </Alert>
      )}

      {!isLoading && !isError && users?.length === 0 && (
        <Typography color="text.secondary">No users yet.</Typography>
      )}

      {hasUsers && users.length > 0 && (
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Username</TableCell>
              <TableCell>Full name</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {users.map((user) => (
              <UserListRow key={user.id} user={user} currentUserId={currentUser?.id} />
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
