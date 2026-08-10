import { useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Navigate, useNavigate } from "react-router";

import { ROLE_HOME_PATH } from "../../components/shell/navigationConfig";
import { useCurrentUser, useLogin } from "../../services/authService";

/**
 * The Login screen, built per key-login.html.
 *
 * One form for all four Roles, no role selector. On success, redirects to
 * the signed-in User's Role home surface (AC3). If a User who is already
 * authenticated visits this page, redirects them away instead of showing
 * the form again.
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
        <Typography variant="h6">Sign in</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", marginBottom: 3 }}>
          Restaurant Kitchen Management System
        </Typography>

        <TextField
          id="username"
          label="Username"
          fullWidth
          margin="normal"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          error={loginMutation.isError}
          autoFocus
        />
        <TextField
          id="password"
          label="Password"
          type="password"
          fullWidth
          margin="normal"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={loginMutation.isError}
        />

        {loginMutation.isError && (
          <Alert severity="error" sx={{ marginTop: 1 }}>
            {loginMutation.error.message}
          </Alert>
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
