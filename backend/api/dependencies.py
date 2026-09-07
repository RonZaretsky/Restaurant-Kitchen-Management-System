from collections.abc import Awaitable, Callable
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Request, WebSocket, WebSocketException

from clients.database import SessionDep, session_scope
from container import Container
from data_models import User, UserRole
from exceptions import AuthError, ForbiddenError
from services.auth_service import COOKIE_NAME, AuthService


@inject
async def get_current_user(
    request: Request,
    db: SessionDep,
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
) -> User:
    """Resolve the authenticated User for the current request.

    The single shared authorization seam for the whole app. Protected routes
    depend on CurrentUserDep below and never re-derive a user from the
    cookie themselves.

    Args:
        request: The incoming request, read for its session cookie.
        db: The active database session.
        auth_service: Injected service that verifies the token.

    Returns:
        The authenticated, active User.

    Raises:
        SessionExpiredError: If the session token has expired.
        NotAuthenticatedError: If no usable session token is present.
    """
    return await auth_service.get_current_user(request.cookies.get(COOKIE_NAME), db)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def verify_ws_session(websocket: WebSocket, auth_service: AuthService) -> User:
    """Verify the session cookie on a WebSocket and resolve its User.

    Reuses the exact same AuthService.get_current_user verification the HTTP
    path uses, so the only WebSocket-specific code is reading the cookie off
    a WebSocket instead of a Request.

    The session is opened per call and closed before returning, deliberately.
    A FastAPI `yield` dependency on a WebSocket route stays open for the life
    of the *connection*, which would pin one pooled database connection per
    open socket and exhaust the pool once concurrent clients exceed
    pool_size + max_overflow. That is also what lets the periodic
    re-verification call this on a tick without accumulating sessions.

    Args:
        websocket: The connection, read for its session cookie.
        auth_service: Service that verifies the token.

    Returns:
        The authenticated, active User.

    Raises:
        WebSocketException: Code 1008 (policy violation), if the token is
            absent, invalid, or expired.
    """
    token = websocket.cookies.get(COOKIE_NAME)
    async with session_scope(websocket.app) as db:
        try:
            return await auth_service.get_current_user(token, db)
        except AuthError as exc:
            raise WebSocketException(code=1008, reason=exc.detail) from exc


@inject
async def get_current_user_ws(
    websocket: WebSocket,
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
) -> User:
    """Resolve the authenticated User for a WebSocket handshake.

    The WebSocket-route counterpart to get_current_user. FastAPI requires
    this as a distinct dependency because a Request-typed dependency does
    not resolve inside a @websocket route at all.

    Args:
        websocket: The incoming WebSocket handshake.
        auth_service: Injected service that verifies the token.

    Returns:
        The authenticated, active User.

    Raises:
        WebSocketException: Code 1008 (policy violation), if the token is
            absent, invalid, or expired. Raising before websocket.accept()
            is what makes FastAPI close the handshake cleanly instead of
            accepting the connection and then immediately dropping it.
    """
    return await verify_ws_session(websocket, auth_service)


CurrentUserWsDep = Annotated[User, Depends(get_current_user_ws)]


@inject
async def verify_ws_origin(
    websocket: WebSocket,
    allow_origin: str = Depends(Provide[Container.config.cors.allow_origin]),
) -> None:
    """Reject a WebSocket handshake whose Origin is not the allowed one.

    CORSMiddleware only inspects the http ASGI scope, so it never sees a
    WebSocket handshake at all. This is the stand-in for the "explicit
    allow-list, never wildcard" CORS rule on that one transport.

    Declared as a route-level dependency so it runs before the session
    cookie is verified, which means a cross-origin handshake is refused
    without costing a JWT decode and a database query.

    Args:
        websocket: The incoming handshake, read for its Origin header.
        allow_origin: The configured frontend origin, the same value
            main.py feeds CORSMiddleware.

    Returns:
        Nothing.

    Raises:
        WebSocketException: Code 1008, if the Origin does not match.
    """
    if websocket.headers.get("origin") != allow_origin:
        raise WebSocketException(code=1008, reason="Origin not allowed")


def require_role(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    """Build a dependency that only permits the given Roles.

    Layers on top of CurrentUserDep rather than re-deriving the user, so
    every route that depends on it is authenticated first (by
    get_current_user) and only then role-checked here: one shared
    dependency, never re-derived per route, over a role-level-only
    permission model.

    Call it, do not pass it. The correct usage is
    `Depends(require_role(UserRole.admin))`. Passing the function itself,
    `Depends(require_role)`, registers without error but makes FastAPI read
    the roles as a query parameter, so the route answers 422 and no
    authorization runs at all.

    Args:
        roles: The Roles permitted to proceed. No roles means no Role is
            permitted, the returned dependency always raises.

    Returns:
        An async dependency that resolves to the current User if their Role
        is in roles, or raises ForbiddenError otherwise.

    Raises:
        TypeError: If any argument is not a UserRole member.
    """
    # UserRole is a plain Enum, so UserRole.admin == "admin" is False. Without
    # this check, require_role("admin") or require_role([UserRole.admin]) would
    # build a guard that silently denies everyone, reported only as a 403 saying
    # the user lacks permission. Fail at import time instead.
    invalid = [role for role in roles if not isinstance(role, UserRole)]
    if invalid:
        raise TypeError(f"require_role expects UserRole members, got {invalid!r}")

    async def _check_role(user: CurrentUserDep) -> User:
        """Reject the current User if their Role is not permitted.

        Args:
            user: The already-authenticated User, resolved by CurrentUserDep.

        Returns:
            The same User, unchanged, if their Role is permitted.

        Raises:
            ForbiddenError: If the User's Role is not in the permitted set.
        """
        if user.role not in roles:
            raise ForbiddenError()
        return user

    return _check_role
