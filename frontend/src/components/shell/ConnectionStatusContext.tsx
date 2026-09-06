import { createContext, useContext, type ReactNode } from "react";

/**
 * "replaced": this tab's own connection was deliberately closed by the server because a newer
 * connection for the same session (typically a second tab) took it over - not a drop, and not
 * retried (see RealtimeProvider's CONNECTION_REPLACED_CLOSE_CODE handling), since retrying would
 * just steal the connection back and repeat the takeover forever.
 */
export type ConnectionStatus = "connected" | "reconnecting" | "replaced";

interface ConnectionStatusContextValue {
  status: ConnectionStatus;
}

/**
 * Transport-agnostic connection signal.
 *
 * Defaults to "connected". RealtimeProvider is the live
 * WebSocket signal that drives this via ConnectionStatusProvider; this
 * default only matters for a consumer rendered outside that provider (there
 * is none today, RealtimeProvider wraps the whole authenticated shell).
 */
export const ConnectionStatusContext = createContext<ConnectionStatusContextValue>({
  status: "connected",
});

/**
 * Reads the current app-wide connection status.
 *
 * @returns The current connection status.
 */
export function useConnectionStatus(): ConnectionStatus {
  return useContext(ConnectionStatusContext).status;
}

/**
 * Provides the connection status to the subtree.
 *
 * @param children - The subtree that can read the connection status.
 * @param status - The status to provide. Defaults to "connected".
 * @returns The wrapped subtree.
 */
export function ConnectionStatusProvider({
  children,
  status = "connected",
}: {
  children: ReactNode;
  status?: ConnectionStatus;
}) {
  return (
    <ConnectionStatusContext.Provider value={{ status }}>{children}</ConnectionStatusContext.Provider>
  );
}
