import Alert from "@mui/material/Alert";

import { useConnectionStatus } from "./ConnectionStatusContext";

/**
 * The one app-wide connection-status banner.
 *
 * Renders nothing while connected. Mounted once in AppShell, above the
 * routed page content, so it is genuinely a single app-wide instance,
 * not one per page.
 *
 * @returns The banner while reconnecting or replaced by another tab, otherwise null.
 */
export function ReconnectingBanner() {
  const status = useConnectionStatus();

  if (status === "reconnecting") {
    return (
      <Alert severity="warning" square>
        Reconnecting...
      </Alert>
    );
  }

  if (status === "replaced") {
    // Not a problem to warn about - the User opened this account in another tab, and this one
    // deliberately does not fight it for the connection back (see RealtimeProvider). "info", not
    // "warning": nothing is broken, live updates just live in the other tab now.
    return (
      <Alert severity="info" square>
        This account is connected in another tab. Reload this tab to make it live again.
      </Alert>
    );
  }

  return null;
}
