from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from clients.database import SessionDep
from container import Container
from data_models import UserRole
from services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])

_COOKIE_NAME = "access_token"


class LoginRequest(BaseModel):
    """Body of a login request."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Body of a successful login response."""

    role: UserRole


@router.post("/login", response_model=LoginResponse)
@inject
async def login(
    payload: LoginRequest,
    response: Response,
    db: SessionDep,
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
    debug: bool = Depends(Provide[Container.config.app.debug]),
) -> LoginResponse:
    """Authenticate a staff member and start a session.

    Args:
        payload: The submitted username and password.
        response: Used to set the session cookie on success.
        db: The active database session.
        auth_service: Injected service handling credential verification and
            token issuance.
        debug: Injected app-debug flag; the cookie's Secure attribute is
            disabled only in local dev, per AD-3.

    Returns:
        The authenticated User's role. The JWT itself is never returned in
        the body, only as an httpOnly cookie.

    Raises:
        InvalidCredentialsError: Propagated from auth_service.authenticate
            for any wrong username, wrong password, or deactivated account,
            handled globally as a generic 401.
    """
    user = await auth_service.authenticate(db, payload.username, payload.password)
    token = auth_service.create_access_token(user)

    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=not debug,
        max_age=auth_service.token_expiry_hours * 3600,
    )

    return LoginResponse(role=user.role)
