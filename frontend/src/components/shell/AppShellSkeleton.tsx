import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Skeleton from "@mui/material/Skeleton";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";

import { RowsSkeleton } from "./RowsSkeleton";

/** How many nav-link placeholders to draw, the median across the four Roles. */
const NAV_PLACEHOLDER_COUNT = 3;

/**
 * The cold-load stand-in for the whole app shell.
 *
 * Renders the app bar's real shape with Skeletons where the nav links and the
 * user chip will land, rather than a blank page, so the first paint after a
 * reload does not visibly jump when the current User resolves. The brand mark
 * is real text because it never depends on who is signed in.
 *
 * @returns The skeleton app bar and a stack of placeholder content rows.
 */
export function AppShellSkeleton() {
  return (
    <>
      <AppBar position="static">
        <Toolbar sx={{ gap: 3 }}>
          <Typography variant="h6" component="div">
            RKMS
          </Typography>
          <Box component="div" sx={{ display: "flex", gap: 1.5, flexGrow: 1 }}>
            {Array.from({ length: NAV_PLACEHOLDER_COUNT }, (_, index) => (
              <Skeleton key={index} variant="text" width={96} sx={{ bgcolor: "rgba(255,255,255,0.3)" }} />
            ))}
          </Box>
          <Skeleton variant="text" width={140} sx={{ bgcolor: "rgba(255,255,255,0.3)" }} />
          <Skeleton variant="circular" width={24} height={24} sx={{ bgcolor: "rgba(255,255,255,0.3)" }} />
        </Toolbar>
      </AppBar>
      <Box component="main" sx={{ padding: 3 }}>
        <RowsSkeleton count={4} />
      </Box>
    </>
  );
}
