import { createContext, useContext, type ReactNode } from "react";

export type ConnectionStatus = "connected" | "reconnecting";

interface ConnectionStatusContextValue {
  status: ConnectionStatus;
}

/**
 * Transport-agnostic connection signal.
 *
 * Defaults to "connected", there is no real transport to observe yet.
 * Story 1.5 replaces this default with a live WebSocket signal; this
 * context's shape (`{ status }`) is the contract that story must match.
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
