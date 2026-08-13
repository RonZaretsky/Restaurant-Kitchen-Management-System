import { useEffect, useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
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

/** Every Role a User can hold, in the order the create/edit Select renders them. */
const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "admin", label: "Admin" },
  { value: "waiter", label: "Waiter" },
  { value: "cook", label: "Cook" },
  { value: "warehouse_manager", label: "Warehouse Manager" },
];

/** Maps a Role's value to its display label (e.g. for the read-only Role chip). */
function roleLabel(role: UserRole): string {
  return ROLE_OPTIONS.find((option) => option.value === role)?.label ?? role;
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
  /** The signed-in Admin's own id, used for AC6's "This is you" marker. */
  currentUserId: number | undefined;
}

/**
 * One row of the Users list, owning its own edit and password-reset state.
 *
 * Mirrors TablesSetupPage's TableListRow: editable fields resync from the
 * server's value only while this row is not mid-edit, so a background
 * refetch (another Admin's concurrent change, or this row's own sibling
 * saving) never clobbers text the Admin is still typing.
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
  const isNameValid = trimmedName.length > 0 && trimmedName.length <= 100;
  const hasChanges = trimmedName !== user.full_name || draftRole !== user.role;
  const canSave = isNameValid && hasChanges && !updateMutation.isPending;

  const startEdit = () => {
    updateMutation.reset();
    setIsEditing(true);
  };

  const cancelEdit = () => {
    updateMutation.reset();
    setDraftFullName(user.full_name);
    setDraftRole(user.role);
    setIsEditing(false);
  };

  const save = () => {
    if (!canSave) {
      return;
    }
    // Only the fields that actually changed are sent: an entirely empty
    // payload is a 422 (the backend requires at least one of full_name/role),
    // so canSave already guards that, but sending an unchanged field back is
    // also unnecessary work the server would just no-op.
    const payload: { full_name?: string; role?: UserRole } = {};
    if (trimmedName !== user.full_name) {
      payload.full_name = trimmedName;
    }
    if (draftRole !== user.role) {
      payload.role = draftRole;
    }
    updateMutation.mutate(
      { userId: user.id, payload },
      { onSuccess: () => setIsEditing(false) },
    );
  };

  const startResetPassword = () => {
    resetPasswordMutation.reset();
    setDraftPassword("");
    setIsResettingPassword(true);
  };

  const cancelResetPassword = () => {
    resetPasswordMutation.reset();
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

  const isSelf = user.id === currentUserId;
  const activeError =
    updateMutation.error ?? deactivateMutation.error ?? reactivateMutation.error ?? resetPasswordMutation.error;

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
              helperText={!isNameValid ? "Full name is required" : undefined}
            />
          ) : (
            user.full_name
          )}
        </TableCell>
        <TableCell>
          {isEditing ? (
            <Select
              size="small"
              aria-label={`Role for ${user.username}`}
              value={draftRole}
              onChange={(event: SelectChangeEvent) => setDraftRole(event.target.value as UserRole)}
            >
              {ROLE_OPTIONS.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          ) : (
            <Chip size="small" label={roleLabel(user.role)} />
          )}
        </TableCell>
        <TableCell>
          <Chip
            size="small"
            label={user.is_active ? "Active" : "Inactive"}
            color={user.is_active ? "success" : "default"}
          />
        </TableCell>
        <TableCell>
          {isEditing ? (
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button size="small" variant="contained" onClick={save} disabled={!canSave}>
                Save
              </Button>
              <Button size="small" onClick={cancelEdit} disabled={updateMutation.isPending}>
                Cancel
              </Button>
            </Box>
          ) : isResettingPassword ? (
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <TextField
                size="small"
                type="password"
                label={`New password for ${user.username}`}
                value={draftPassword}
                onChange={(event) => setDraftPassword(event.target.value)}
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
          ) : (
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
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
              {user.is_active && !isSelf && (
                <Button
                  size="small"
                  color="error"
                  onClick={() => deactivateMutation.mutate(user.id)}
                  disabled={deactivateMutation.isPending}
                >
                  Deactivate
                </Button>
              )}
              {!user.is_active && (
                <Button
                  size="small"
                  onClick={() => reactivateMutation.mutate(user.id)}
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
 * each row supporting inline edit, deactivate/reactivate, and password
 * reset. The signed-in Admin's own row shows "This is you" in place of
 * Deactivate (AC6), so self-deactivation is never reachable from this
 * screen. The last-active-Admin lockout (AD-15) is enforced server-side;
 * this page only surfaces its 409 inline.
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

  const canSubmit =
    username.trim().length > 0 &&
    fullName.trim().length > 0 &&
    password.length > 0 &&
    !createMutation.isPending;

  const handleCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    createMutation.mutate(
      { username: username.trim(), full_name: fullName.trim(), role, password },
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

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        Users
      </Typography>
      {users && (
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {`${users.length} staff accounts · ${activeCount} active`}
        </Typography>
      )}

      <Box
        component="form"
        onSubmit={handleCreate}
        sx={{ display: "flex", flexDirection: "row", gap: 1, alignItems: "center", flexWrap: "wrap", marginBottom: 3 }}
      >
        <TextField
          size="small"
          label="Username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
        />
        <TextField
          size="small"
          label="Full name"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
        />
        <Select
          size="small"
          aria-label="Role"
          value={role}
          onChange={(event: SelectChangeEvent) => setRole(event.target.value as UserRole)}
        >
          {ROLE_OPTIONS.map((option) => (
            <MenuItem key={option.value} value={option.value}>
              {option.label}
            </MenuItem>
          ))}
        </Select>
        <TextField
          size="small"
          type="password"
          label="Initial password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
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

      {!isLoading && !isError && users && users.length > 0 && (
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Username</TableCell>
              <TableCell>Full name</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Actions</TableCell>
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
