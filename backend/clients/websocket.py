import asyncio
import json
from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import WebSocket

from data_models import UserRole

# One slow client must not eat the whole real-time delivery budget for everyone
# else, so a send that has not completed in this long is abandoned and that
# connection is dropped.
SEND_TIMEOUT_SECONDS = 1.0

# A private-use WebSocket close code (RFC 6455 §7.4.2 reserves 4000-4999 for
# applications) for the one case in `register` below where this server closes a
# connection deliberately, not because anything failed: a second tab (or any new
# connection for the same User) just took the socket over. Distinct from a default
# close so the client (frontend/src/components/shell/RealtimeProvider.tsx) can tell
# "you were replaced" apart from "the network dropped" and not auto-retry into an
# infinite tug-of-war with the connection that replaced it.
CONNECTION_REPLACED_CLOSE_CODE = 4409


@dataclass
class _Connection:
    """One open socket plus the identity it was authenticated as."""

    user_id: int
    role: UserRole
    websocket: WebSocket


class ConnectionRegistry:
    """Tracks open WebSocket connections by the User holding them.

    Keyed by user id rather than by Role alone so that a broadcast can be
    Role-scoped while the registry still enforces one
    connection per authenticated session: registering a second socket for a
    User closes that User's previous one.
    """

    def __init__(self, logger: Any) -> None:
        """Initialize an empty registry.

        Args:
            logger: Injected loguru logger.
        """
        self._connections: dict[int, _Connection] = {}
        self._logger = logger

    async def register(self, user_id: int, role: UserRole, websocket: WebSocket) -> None:
        """Record a newly accepted connection, replacing any the User already held.

        Closing the previous socket is what makes "one connection per
        authenticated session" literally true, and it bounds memory against a
        client that opens sockets in a loop. The trade-off is deliberate: a
        second tab takes the connection over from the first.

        The dict entry is swapped to the new connection *before* awaiting the
        old one's close, not after. Closing is an await, and a broadcast
        concurrent with this call must see the new connection as soon as it
        exists rather than during a window where the entry is still the
        (already-closing) old one.

        Args:
            user_id: The connecting User's id.
            role: The connecting User's Role.
            websocket: The accepted connection.

        Returns:
            Nothing.
        """
        existing = self._connections.get(user_id)
        self._connections[user_id] = _Connection(user_id=user_id, role=role, websocket=websocket)
        if existing is not None:
            self._logger.info(
                "Replacing existing WebSocket connection for user_id={}", user_id
            )
            await self._close_quietly(existing.websocket, code=CONNECTION_REPLACED_CLOSE_CODE)

    def unregister(self, user_id: int, websocket: WebSocket) -> None:
        """Drop a connection, e.g. once it disconnects.

        Only drops the entry if it still holds this exact socket. Without
        that check, a disconnecting socket that had already been replaced by
        a reconnect would evict the live replacement.

        Args:
            user_id: The User the connection was registered under.
            websocket: The connection to drop.

        Returns:
            Nothing.
        """
        existing = self._connections.get(user_id)
        if existing is not None and existing.websocket is websocket:
            del self._connections[user_id]

    async def broadcast_to_roles(
        self, roles: Iterable[UserRole], event: str, payload: dict[str, Any]
    ) -> None:
        """Send one `{domain}.{event}` message to every connection in those Roles.

        Serializes once, up front: a payload carrying a value json cannot
        encode is a bug in the *sender*, not a dead client, so it is logged
        and aborts the whole broadcast rather than being mistaken for a
        transport failure and silently unsubscribing healthy clients.

        Sends run concurrently with a per-send timeout, so one client with a
        full send buffer cannot delay delivery to everyone else past the
        real-time budget. A send that fails or times out unregisters just that
        connection.

        Args:
            roles: Which Roles' connections receive this message. A single
                UserRole is accepted and treated as a one-element group.
            event: The `{domain}.{event}` name, e.g. "order.item_status_changed".
            payload: The JSON-serializable event body.

        Returns:
            Nothing.
        """
        targets = self._targets(roles)
        if not targets:
            return

        try:
            message = json.dumps({"event": event, "payload": payload})
        except (TypeError, ValueError):
            self._logger.exception(
                "Refusing to broadcast {}: payload is not JSON-serializable", event
            )
            return

        await asyncio.gather(*(self._send(connection, message, event) for connection in targets))

    async def close_all(self) -> None:
        """Close every open connection.

        Called once, on app shutdown, so no socket is left dangling when the
        server process exits. Each close is isolated: a socket the server has
        already closed raises, and that must not stop the rest from being
        closed.

        Returns:
            Nothing.
        """
        for connection in list(self._connections.values()):
            await self._close_quietly(connection.websocket)
        self._connections.clear()

    def _targets(self, roles: Iterable[UserRole]) -> list[_Connection]:
        """Select the connections belonging to any of the given Roles.

        Args:
            roles: The Roles to select, or a single UserRole.

        Returns:
            The matching connections, as a snapshot safe to iterate while
            sends mutate the registry.
        """
        wanted = {roles} if isinstance(roles, UserRole) else set(roles)
        return [c for c in self._connections.values() if c.role in wanted]

    async def _send(self, connection: _Connection, message: str, event: str) -> None:
        """Deliver one already-serialized message to one connection.

        Args:
            connection: The target connection.
            message: The serialized envelope.
            event: The event name, for logging only.

        Returns:
            Nothing.
        """
        try:
            await asyncio.wait_for(
                connection.websocket.send_text(message), timeout=SEND_TIMEOUT_SECONDS
            )
        except Exception:
            self._logger.warning(
                "Dropping WebSocket connection for user_id={} after {} failed to send",
                connection.user_id,
                event,
            )
            self.unregister(connection.user_id, connection.websocket)

    async def _close_quietly(self, websocket: WebSocket, code: int = 1000) -> None:
        """Close a socket, ignoring the error from one already closed.

        Args:
            websocket: The connection to close.
            code: The WebSocket close code to send. Defaults to 1000 (normal closure),
                used by `close_all` on shutdown; `register` passes
                `CONNECTION_REPLACED_CLOSE_CODE` for a takeover close instead.

        Returns:
            Nothing.
        """
        try:
            await websocket.close(code=code)
        except Exception:
            pass
