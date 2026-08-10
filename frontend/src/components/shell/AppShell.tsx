import type { CSSProperties } from "react";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import { NavLink, Outlet } from "react-router";

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

const navLinkStyle = ({ isActive }: { isActive: boolean }): CSSProperties => ({
  color: "inherit",
  textDecoration: "none",
  padding: "8px 14px",
  borderRadius: 4,
  fontSize: "0.8125rem",
  backgroundColor: isActive ? "rgba(255,255,255,0.18)" : "transparent",
  fontWeight: isActive ? 500 : 400,
});

/**
 * The app bar, the current Role's own nav, and the routed page content.
 *
 * Only ever rendered once the current User is known, RequireAuth is the
 * caller that guarantees this. Nav links come only from
 * ROLE_NAV_ITEMS[user.role], which is the literal mechanism behind AC2's
 * "no cross-role navigation anywhere."
 *
 * @param user - The authenticated User whose Role drives the nav.
 * @returns The app shell chrome wrapping the active route's page.
 */
export function AppShell({ user }: { user: CurrentUser }) {
  const navItems = ROLE_NAV_ITEMS[user.role];

  return (
    <>
      <AppBar position="static">
        <Toolbar sx={{ gap: 3 }}>
          <Typography variant="h6" component="div">
            RKMS
          </Typography>
          <Box component="nav" sx={{ display: "flex", gap: 0.5, flexGrow: 1 }}>
            {navItems.map((item) => (
              <NavLink key={item.path} to={item.path} style={navLinkStyle}>
                {item.label}
              </NavLink>
            ))}
          </Box>
          <Typography variant="body2">
            {user.full_name} · {ROLE_LABELS[user.role]}
          </Typography>
          <ThemeToggle />
        </Toolbar>
      </AppBar>
      <ReconnectingBanner />
      <Box component="main" sx={{ padding: 3 }}>
        <Outlet />
      </Box>
    </>
  );
}
