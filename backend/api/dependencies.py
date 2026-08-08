from collections.abc import Awaitable, Callable
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Request

from clients.database import SessionDep
from container import Container
from data_models import User, UserRole
from exceptions import ForbiddenError
from services.auth_service import COOKIE_NAME, AuthService


@inject
async def get_current_user(
    request: Request,
    db: SessionDep,
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
) -> User:
    """Resolve the authenticated User for the current request.

    The single shared authorization seam required by AD-3. Protected routes
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


def require_role(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    """Build a dependency that only permits the given Roles.

    Layers on top of CurrentUserDep rather than re-deriving the user, so
    every route that depends on it is authenticated first (by
    get_current_user) and only then role-checked here, per AD-3's "one
    shared dependency, never re-derived per route" and AD-9's role-level-only
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
