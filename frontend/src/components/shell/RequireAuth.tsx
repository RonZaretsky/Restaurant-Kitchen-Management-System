import Box from "@mui/material/Box";
import { Navigate, useLocation } from "react-router";

import { useCurrentUser } from "../../services/authService";
import { AppShell } from "./AppShell";
import { RowsSkeleton } from "./RowsSkeleton";
import { ROLE_HOME_PATH, ROLE_PATH_PREFIX } from "./navigationConfig";

/**
 * Gates every protected route behind authentication and Role scoping.
 *
 * Reads useCurrentUser() directly rather than duplicating it into a
 * separate Context, that would be exactly the "server data duplicated into
 * ad-hoc local/global state" AD-13 prohibits.
 *
 * Three states: while the current-user query is loading, render a loading
 * skeleton (AC6); if it errors (no valid session), redirect to Login
 * (AC1); otherwise redirect "/" and any URL outside the User's own Role
 * prefix to that Role's home surface, and render the app shell for
 * everything else (AC2).
 *
 * @returns A loading skeleton, a redirect, or the AppShell wrapping the
 *   matched child route.
 */
export function RequireAuth() {
  const { data: user, isLoading, isError } = useCurrentUser();
  const location = useLocation();

  if (isLoading) {
    return (
      <Box sx={{ padding: 3 }}>
        <RowsSkeleton count={3} />
      </Box>
    );
  }

  if (isError || !user) {
    return <Navigate to="/login" replace />;
  }

  const homePath = ROLE_HOME_PATH[user.role];
  const isWithinOwnRole = location.pathname.startsWith(ROLE_PATH_PREFIX[user.role]);

  if (location.pathname === "/" || !isWithinOwnRole) {
    return <Navigate to={homePath} replace />;
  }

  return <AppShell user={user} />;
}
