import asyncio
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, WebSocketException

from api.dependencies import CurrentUserWsDep, verify_ws_origin, verify_ws_session
from container import Container
from services.auth_service import AuthService
from services.realtime_service import RealtimeService

router = APIRouter()

# How often an accepted connection re-checks that its session is still valid.
# Authorization is otherwise only decided at the handshake, which would let a
# socket outlive its JWT (and survive a deactivation or a Role change) for as
# long as the tab stays open. Module-level so tests can shorten it.
REVERIFY_INTERVAL_SECONDS = 60.0


@router.websocket("/api/ws", dependencies=[Depends(verify_ws_origin)])
@inject
async def websocket_endpoint(
    websocket: WebSocket,
    user: CurrentUserWsDep,
    realtime_service: RealtimeService = Depends(Provide[Container.realtime_service]),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
    logger: Any = Depends(Provide[Container.logging]),
) -> None:
    """The single push channel every authenticated session connects to.

    Scoped to the connecting User's Role (AD-2): registered under user.role,
    so a broadcast can target that Role specifically. Read-only from the
    client's perspective: inbound frames are received only to detect a
    disconnect, never acted on (AD-2: "Clients never treat the WebSocket as
    a write channel"), and never decoded, so a binary frame cannot fault the
    handler.

    The Origin allow-list is enforced by the verify_ws_origin route
    dependency, which runs before the session cookie is read.

    Args:
        websocket: The incoming connection.
        user: The authenticated User, resolved and Role-checked by
            get_current_user_ws before this body runs.
        realtime_service: Injected service used to register/unregister this
            connection.
        auth_service: Injected service used to re-verify the session
            periodically for as long as the connection is open.
        logger: Injected loguru logger.

    Returns:
        Nothing. Runs until the client disconnects or the session stops
        verifying.
    """
    await websocket.accept()
    await realtime_service.register(user.id, user.role, websocket)
    logger.info("WebSocket connected for user_id={} role={}", user.id, user.role.value)

    reverifier = asyncio.create_task(_reverify_until_invalid(websocket, user.id, auth_service, logger))
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        reverifier.cancel()
        realtime_service.unregister(user.id, websocket)
        logger.info("WebSocket disconnected for user_id={}", user.id)


async def _reverify_until_invalid(
    websocket: WebSocket, user_id: int, auth_service: AuthService, logger: Any
) -> None:
    """Close the connection once its session no longer verifies.

    Runs alongside the receive loop rather than inside it, so re-verification
    never has to cancel an in-flight receive. Closing the socket here makes
    the receive loop observe a disconnect and unwind normally.

    Args:
        websocket: The open connection to re-check and, on failure, close.
        user_id: The connected User's id, for logging.
        auth_service: Service that verifies the session token.
        logger: Injected loguru logger.

    Returns:
        Nothing. Returns once the session has been rejected; otherwise runs
        until cancelled.
    """
    while True:
        await asyncio.sleep(REVERIFY_INTERVAL_SECONDS)
        try:
            await verify_ws_session(websocket, auth_service)
        except WebSocketException as exc:
            logger.warning(
                "Closing WebSocket for user_id={}, session no longer valid: {}",
                user_id,
                exc.reason,
            )
            await websocket.close(code=exc.code, reason=exc.reason)
            return
