import LogoutIcon from "@mui/icons-material/Logout";
import Alert from "@mui/material/Alert";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import { styled } from "@mui/material/styles";
import { NavLink, Outlet } from "react-router";

import { useLogout } from "../../services/authService";
import { ApiError } from "../../services/httpClient";
import type { CurrentUser, UserRole } from "../../types/user";
import { ReconnectingBanner } from "./ReconnectingBanner";
import { ThemeToggle } from "./ThemeToggle";
import { ROLE_NAV_ITEMS } from "./navigationConfig";

const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Admin",
  waiter: "Waiter",
  cook: "Cook",
  warehouse_manager: "Warehouse Manager",
};

/**
 * A nav link in the app bar.
 *
 * Styled rather than given an inline `style` callback so the active and
 * focus-visible states can be expressed as real CSS. NavLink appends its own
 * `active` class on top of the one MUI generates, which is what `&.active`
 * hooks into.
 *
 * The active background is a darkened wash, not a lightened one. Over the
 * light theme's `#0B6E8F` app bar, lightening drops white label text to about
 * 4.03:1 and fails WCAG 2.2 AA, while darkening lifts it to roughly 7.9:1 and
 * passes in both themes (AC8). The focus ring uses `currentColor` because the
 * app bar's text is light in both themes while its background is not.
 */
const NavItem = styled(NavLink)(({ theme }) => ({
  color: "inherit",
  textDecoration: "none",
  padding: "8px 14px",
  borderRadius: theme.shape.borderRadius,
  fontSize: theme.typography.pxToRem(13),
  "&:focus-visible": {
    outline: "2px solid currentColor",
    outlineOffset: 2,
  },
  "&.active": {
    backgroundColor: "rgba(0,0,0,0.2)",
    fontWeight: 500,
  },
}));

/**
 * The app bar, the current Role's own nav, and the routed page content.
 *
 * Only ever rendered once the current User is known, RequireAuth is the caller
 * that guarantees this. Nav links come only from ROLE_NAV_ITEMS[user.role],
 * which is the literal mechanism behind AC2's "only surfaces that Role is
 * authorized for." Note that an entry may cross a URL prefix when the backend
 * authorizes that Role for it (Admin's Ingredients entry, Story 2.6); the
 * invariant is authorization, not the prefix.
 *
 * @param user - The authenticated User whose Role drives the nav.
 * @returns The app shell chrome wrapping the active route's page.
 */
export function AppShell({ user }: { user: CurrentUser }) {
  const navItems = ROLE_NAV_ITEMS[user.role];
  const logoutMutation = useLogout();

  return (
    <>
      <AppBar position="static">
        <Toolbar sx={{ gap: 3 }}>
          <Typography variant="h6" component="div">
            RKMS
          </Typography>
          <Box component="nav" sx={{ display: "flex", gap: 0.5, flexGrow: 1 }}>
            {navItems.map((item) => (
              <NavItem key={item.path} to={item.path}>
                {item.label}
              </NavItem>
            ))}
          </Box>
          <Typography variant="body2">
            {user.full_name} · {ROLE_LABELS[user.role]}
          </Typography>
          <ThemeToggle />
          <IconButton
            color="inherit"
            onClick={() => logoutMutation.mutate()}
            disabled={logoutMutation.isPending}
            aria-label="Sign out"
          >
            <LogoutIcon />
          </IconButton>
        </Toolbar>
      </AppBar>
      {logoutMutation.isError && (
        <Alert severity="error">
          {logoutMutation.error instanceof ApiError
            ? logoutMutation.error.message
            : "Could not sign out. Try again."}
        </Alert>
      )}
      <ReconnectingBanner />
      <Box component="main" sx={{ padding: 3 }}>
        <Outlet />
      </Box>
    </>
  );
}
