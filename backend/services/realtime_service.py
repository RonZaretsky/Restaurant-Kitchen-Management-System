from typing import Any, Iterable

from fastapi import WebSocket

from clients.websocket import ConnectionRegistry
from data_models import UserRole


class RealtimeService:
    """Emits `{domain}.{event}` push notifications to connected clients, by Role.

    A thin wrapper over ConnectionRegistry so api/websocket.py calls into
    services/ rather than clients/ directly (AD-1). This is also the seam
    later domain services (order_service, kitchen_service, inventory_service)
    will inject to push their own state changes once they exist.
    """

    def __init__(self, registry: ConnectionRegistry, logger: Any) -> None:
        """Initialize the service.

        Args:
            registry: The connection registry to delegate to.
            logger: The loguru logger injected from the container.
        """
        self._registry = registry
        self._logger = logger

    async def register(self, user_id: int, role: UserRole, websocket: WebSocket) -> None:
        """Record a newly accepted connection, replacing any the User already held.

        Args:
            user_id: The connecting User's id.
            role: The connecting User's Role.
            websocket: The accepted connection.

        Returns:
            Nothing.
        """
        await self._registry.register(user_id, role, websocket)

    def unregister(self, user_id: int, websocket: WebSocket) -> None:
        """Drop a connection, e.g. once it disconnects.

        Args:
            user_id: The User the connection was registered under.
            websocket: The connection to drop.

        Returns:
            Nothing.
        """
        self._registry.unregister(user_id, websocket)

    async def broadcast(
        self, roles: Iterable[UserRole], event: str, payload: dict[str, Any]
    ) -> None:
        """Push one `{domain}.{event}` message to every connection in those Roles.

        Takes a group of Roles rather than one, so an event several Roles
        care about (order.item_status_changed reaches both cooks and waiters)
        is emitted exactly once by the service that owns the mutation (AC4),
        instead of once per audience.

        Args:
            roles: Which Roles' connections receive this message. A single
                UserRole is accepted and treated as a one-element group.
            event: The `{domain}.{event}` name, e.g. "order.item_status_changed".
            payload: The JSON-serializable event body.

        Returns:
            Nothing.
        """
        names = [roles.value] if isinstance(roles, UserRole) else [role.value for role in roles]
        self._logger.info("Broadcasting {} to roles={}", event, names)
        await self._registry.broadcast_to_roles(roles, event, payload)
