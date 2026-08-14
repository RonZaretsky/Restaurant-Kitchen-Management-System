import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import { Navigate, useLocation } from "react-router";

import { useCurrentUser } from "../../services/authService";
import { ApiError } from "../../services/httpClient";
import { AppShell } from "./AppShell";
import { AppShellSkeleton } from "./AppShellSkeleton";
import { canRoleVisit, ROLE_HOME_PATH } from "./navigationConfig";
import { RealtimeProvider } from "./RealtimeProvider";

/**
 * Gates every protected route behind authentication and Role scoping.
 *
 * Reads useCurrentUser() directly rather than duplicating it into a separate
 * Context, that would be exactly the "server data duplicated into ad-hoc
 * local/global state" AD-13 prohibits.
 *
 * Four states: while the current-user query is loading, render the shell's
 * cold-load skeleton (AC6); if it failed for any reason other than a rejected
 * session, offer a retry rather than signing the User out; if the session
 * itself is invalid, redirect to Login (AC1); otherwise redirect "/" and any
 * URL the Role cannot visit to that Role's home surface, and render the app
 * shell for everything else (AC2). What a Role can visit is canRoleVisit's
 * call, derived from navigationConfig so a nav entry and its reachability
 * cannot drift apart.
 *
 * The Role prefix check is a navigation affordance, not a security boundary,
 * the backend's require_role is the only real enforcement.
 *
 * @returns A loading skeleton, a retry prompt, a redirect, or the AppShell
 *   wrapping the matched child route.
 */
export function RequireAuth() {
  const { data: user, isLoading, isError, error, refetch } = useCurrentUser();
  const location = useLocation();

  if (isLoading) {
    return <AppShellSkeleton />;
  }

  // Only a 401 means "not signed in". A dead network, a timeout, or a 500 all
  // arrive here as errors too, and redirecting on those would silently sign a
  // working session out of the UI over a momentary blip.
  const isSessionRejected = error instanceof ApiError && error.status === 401;

  if (isError && !isSessionRejected) {
    return (
      <Box sx={{ padding: 3, display: "flex", justifyContent: "center" }}>
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" onClick={() => void refetch()}>
              Retry
            </Button>
          }
        >
          {error?.message ?? "Cannot reach the server."}
        </Alert>
      </Box>
    );
  }

  if (isError || !user) {
    return <Navigate to="/login" replace />;
  }

  const homePath = ROLE_HOME_PATH[user.role];

  if (location.pathname === "/" || !canRoleVisit(user.role, location.pathname)) {
    return <Navigate to={homePath} replace />;
  }

  return (
    <RealtimeProvider>
      <AppShell user={user} />
    </RealtimeProvider>
  );
}
