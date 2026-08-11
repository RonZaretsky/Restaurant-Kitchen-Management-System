import Alert from "@mui/material/Alert";

import { useConnectionStatus } from "./ConnectionStatusContext";

/**
 * The one app-wide "Reconnecting..." banner.
 *
 * Renders nothing while connected. Mounted once in AppShell, above the
 * routed page content, so it is genuinely a single app-wide instance
 * (AC7), not one per page.
 *
 * @returns The banner while reconnecting, otherwise null.
 */
export function ReconnectingBanner() {
  const status = useConnectionStatus();

  if (status !== "reconnecting") {
    return null;
  }

  return (
    <Alert severity="warning" square>
      Reconnecting...
    </Alert>
  );
}
