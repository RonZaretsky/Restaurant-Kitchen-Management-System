import { useState, type FormEvent } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Navigate, useNavigate } from "react-router";

import { ROLE_HOME_PATH } from "../../components/shell/navigationConfig";
import { useCurrentUser, useLogin } from "../../services/authService";
import { ApiError } from "../../services/httpClient";

/** The id the error line is published under, so both fields can point at it. */
const ERROR_MESSAGE_ID = "login-error";

/** The one credentials message, identical for a bad username and a bad password. */
const INVALID_CREDENTIALS_MESSAGE = "Invalid username or password";

/** Shown for anything that is not a rejected credential and not a reachability problem. */
const UNEXPECTED_ERROR_MESSAGE = "Something went wrong. Try again.";

/**
 * Picks the copy to show under the form for a failed login.
 *
 * A rejected credential always renders the same generic line whichever field
 * was wrong (AC3, FR-1), so the form never reveals whether a username exists.
 * Reachability failures carry their own already-user-safe text from
 * httpClient, since "the server is down" is genuinely useful and gives nothing
 * away. Everything else, including a validation 422, collapses to a neutral
 * fallback rather than leaking a backend or browser string into the UI.
 *
 * @param error - The error the login mutation failed with.
 * @returns The message to display.
 */
function loginErrorMessage(error: Error): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return INVALID_CREDENTIALS_MESSAGE;
    }
    if (error.status === 0) {
      return error.message;
    }
  }
  return UNEXPECTED_ERROR_MESSAGE;
}

/**
 * The Login screen, built per key-login.html.
 *
 * One form for all four Roles, no role selector. On success, redirects to the
 * signed-in User's Role home surface (AC3). If a User who is already
 * authenticated visits this page, redirects them away instead of showing the
 * form again.
 *
 * @returns The login form, or a redirect for an already-authenticated visitor.
 */
export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const loginMutation = useLogin();
  const { data: currentUser, isSuccess: isAlreadyAuthenticated } = useCurrentUser();

  if (isAlreadyAuthenticated && currentUser) {
    return <Navigate to={ROLE_HOME_PATH[currentUser.role]} replace />;
  }

  // Clear a previous failure as soon as the User starts correcting it, so a
  // stale red line does not sit under a form they have already fixed.
  const handleFieldChange = (setter: (value: string) => void) => (value: string) => {
    if (loginMutation.isError) {
      loginMutation.reset();
    }
    setter(value);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    loginMutation.mutate(
      { username, password },
      {
        onSuccess: (data) => {
          navigate(ROLE_HOME_PATH[data.role], { replace: true });
        },
      },
    );
  };

  const errorMessageId = loginMutation.isError ? ERROR_MESSAGE_ID : undefined;

  return (
    <Box
      sx={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
      }}
    >
      <Paper component="form" onSubmit={handleSubmit} sx={{ width: 380, padding: 4 }}>
        <Typography variant="subtitle2" color="primary" gutterBottom>
          RKMS
        </Typography>
        <Typography variant="h6" component="h1">
          Sign in
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", marginBottom: 3 }}>
          Restaurant Kitchen Management System
        </Typography>

        <TextField
          id="username"
          name="username"
          label="Username"
          fullWidth
          required
          margin="normal"
          value={username}
          onChange={(event) => handleFieldChange(setUsername)(event.target.value)}
          error={loginMutation.isError}
          slotProps={{ htmlInput: { autoComplete: "username", "aria-describedby": errorMessageId } }}
          autoFocus
        />
        <TextField
          id="password"
          name="password"
          label="Password"
          type="password"
          fullWidth
          required
          margin="normal"
          value={password}
          onChange={(event) => handleFieldChange(setPassword)(event.target.value)}
          error={loginMutation.isError}
          slotProps={{
            htmlInput: { autoComplete: "current-password", "aria-describedby": errorMessageId },
          }}
        />

        {loginMutation.isError && (
          <Typography
            id={ERROR_MESSAGE_ID}
            role="alert"
            variant="caption"
            color="error"
            sx={{ display: "block", marginTop: 1 }}
          >
            {"⚠ "}
            {loginErrorMessage(loginMutation.error)}
          </Typography>
        )}

        <Button
          type="submit"
          variant="contained"
          fullWidth
          sx={{ marginTop: 3 }}
          disabled={loginMutation.isPending}
        >
          Sign in
        </Button>
      </Paper>
    </Box>
  );
}
