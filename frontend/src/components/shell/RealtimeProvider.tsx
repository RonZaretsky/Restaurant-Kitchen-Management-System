import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import config from "../../config/config";
import { ConnectionStatusProvider, type ConnectionStatus } from "./ConnectionStatusContext";

/** One push notification, in the `{domain}.{event}` envelope every emitter uses. */
interface RealtimeMessage {
  event: string;
  payload: unknown;
}

type Handler = (payload: unknown) => void;

interface RealtimeContextValue {
  /**
   * Subscribes to one `{domain}.{event}` name.
   *
   * @param event - The exact event name to listen for, e.g. "order.item_status_changed".
   * @param handler - Called with the event's payload each time it arrives.
   * @returns A function that removes this subscription.
   */
  subscribe: (event: string, handler: Handler) => () => void;
}

const RealtimeContext = createContext<RealtimeContextValue | undefined>(undefined);

/** Initial reconnect delay, and the delay's ceiling once it has backed off repeatedly. */
const INITIAL_RETRY_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 30000;

/**
 * WebSocket close code the backend sends for a policy rejection: an absent,
 * invalid, or expired session, or a disallowed Origin (see backend/api/websocket.py
 * and backend/api/dependencies.py). Unlike a dropped connection, retrying
 * against this is pointless until the User re-authenticates, so it is not
 * retried the way a transient close is.
 */
const POLICY_VIOLATION_CLOSE_CODE = 1008;

/**
 * WebSocket close code the backend sends when a newer connection for the same session (typically
 * a second browser tab) has taken this socket's place (see ConnectionRegistry.register in
 * backend/clients/websocket.py). Also not retried: reconnecting would just steal the connection
 * back from whichever tab now holds it, and that tab would then reconnect and steal it right
 * back, flapping between the two forever instead of settling.
 */
const CONNECTION_REPLACED_CLOSE_CODE = 4409;

/**
 * Reads the realtime channel's subscribe function.
 *
 * @returns The subscribe function for `{domain}.{event}` push notifications.
 * @throws Error if called outside a RealtimeProvider.
 */
export function useRealtime(): RealtimeContextValue {
  const context = useContext(RealtimeContext);
  if (!context) {
    throw new Error("useRealtime must be used within a RealtimeProvider");
  }
  return context;
}

/**
 * Derives the WebSocket URL from the configured API base URL.
 *
 * Resolves against window.location.origin rather than a plain string
 * replace, so a relative base URL (e.g. "/api", a common same-origin
 * deployment choice) still produces a valid absolute ws(s):// URL instead of
 * a malformed one.
 *
 * @returns The `/api/ws` URL to connect to.
 */
function websocketUrl(): string {
  const httpUrl = new URL(config.api.baseUrl, window.location.origin);
  httpUrl.protocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
  httpUrl.pathname = `${httpUrl.pathname.replace(/\/$/, "")}/api/ws`;
  return httpUrl.toString();
}

/**
 * Narrows a parsed WebSocket frame to the `{event, payload}` shape.
 *
 * `JSON.parse` happily returns `null`, a number, or an array for
 * syntactically valid JSON that is not the envelope this app expects;
 * reading `.event` off any of those throws. Checked explicitly instead.
 *
 * @param value - The result of JSON.parse on an incoming frame.
 * @returns Whether value is a usable RealtimeMessage.
 */
function isRealtimeMessage(value: unknown): value is RealtimeMessage {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { event?: unknown }).event === "string"
  );
}

/**
 * Owns the app's single WebSocket connection and drives the
 * transport-agnostic `ConnectionStatusContext` from its real state.
 *
 * Mounted only inside RequireAuth's authenticated subtree, never at App.tsx's
 * top level: the backend rejects an unauthenticated handshake anyway,
 * and retrying against /api/ws from the pre-login screen would be pure
 * waste. Retries with capped exponential backoff on a transient close, reset
 * to the initial delay once a connection succeeds. A 1008 policy
 * close (expired session, disallowed Origin) is not retried, since nothing
 * will change until the User signs in again; the status is left at
 * "reconnecting" so the shell still shows something is wrong, rather than
 * silently claiming "connected". The client never sends anything over the
 * socket (clients never treat the WebSocket as a write channel), it
 * only receives.
 *
 * @param children - The subtree that can read connection status and
 *   subscribe to push events.
 * @returns The wrapped subtree, with both contexts provided.
 */
export function RealtimeProvider({ children }: { children: ReactNode }) {
  // Starts "connected" rather than "reconnecting": nothing has dropped yet at
  // first mount, and starting at "reconnecting" flashed the warning banner on
  // every login and every reload until the first handshake completed.
  // ConnectionStatusContext's own default is "connected" for the same reason.
  const [status, setStatus] = useState<ConnectionStatus>("connected");
  const handlersRef = useRef<Map<string, Set<Handler>>>(new Map());
  const retryDelayRef = useRef(INITIAL_RETRY_DELAY_MS);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const socketRef = useRef<WebSocket | null>(null);
  const unmountedRef = useRef(false);

  useEffect(() => {
    unmountedRef.current = false;

    function connect(): void {
      if (unmountedRef.current) {
        return;
      }

      const scheduleRetry = () => {
        if (unmountedRef.current) {
          return;
        }
        setStatus("reconnecting");
        retryTimerRef.current = setTimeout(connect, retryDelayRef.current);
        retryDelayRef.current = Math.min(retryDelayRef.current * 2, MAX_RETRY_DELAY_MS);
      };

      let socket: WebSocket;
      try {
        socket = new WebSocket(websocketUrl());
      } catch {
        // New WebSocket() throws synchronously for a malformed URL or a
        // browser-level SecurityError. Without this, that exception would
        // escape the effect and no retry would ever be scheduled.
        scheduleRetry();
        return;
      }
      socketRef.current = socket;

      socket.onopen = () => {
        retryDelayRef.current = INITIAL_RETRY_DELAY_MS;
        setStatus("connected");
      };

      socket.onmessage = (messageEvent: MessageEvent<string>) => {
        let parsed: unknown;
        try {
          parsed = JSON.parse(messageEvent.data);
        } catch {
          return;
        }
        if (!isRealtimeMessage(parsed)) {
          return;
        }
        const handlers = handlersRef.current.get(parsed.event);
        handlers?.forEach((handler) => {
          try {
            handler(parsed.payload);
          } catch {
            // One subscriber throwing must not stop delivery to the others
            // subscribed to the same event.
          }
        });
      };

      socket.onclose = (closeEvent: CloseEvent) => {
        // A superseded socket (one connect() already replaced by a later one)
        // can still fire onclose after the fact; only the current socket's
        // close should drive status or schedule a retry.
        if (socketRef.current !== socket) {
          return;
        }
        if (closeEvent.code === POLICY_VIOLATION_CLOSE_CODE) {
          setStatus("reconnecting");
          return;
        }
        if (closeEvent.code === CONNECTION_REPLACED_CLOSE_CODE) {
          setStatus("replaced");
          return;
        }
        scheduleRetry();
      };
      socket.onerror = () => socket.close();
    }

    connect();

    return () => {
      unmountedRef.current = true;
      clearTimeout(retryTimerRef.current);
      const socket = socketRef.current;
      if (socket) {
        socket.onclose = null;
        socket.onerror = null;
        socket.close();
      }
    };
  }, []);

  const subscribe = useCallback((event: string, handler: Handler) => {
    const handlers = handlersRef.current;
    if (!handlers.has(event)) {
      handlers.set(event, new Set());
    }
    handlers.get(event)!.add(handler);

    return () => {
      handlers.get(event)?.delete(handler);
    };
  }, []);

  return (
    <RealtimeContext.Provider value={{ subscribe }}>
      <ConnectionStatusProvider status={status}>{children}</ConnectionStatusProvider>
    </RealtimeContext.Provider>
  );
}
