from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Request

from clients.database import SessionDep
from container import Container
from data_models import User
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
