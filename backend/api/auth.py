from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from clients.database import SessionDep
from container import Container
from data_models import LoginRequest, LoginResponse
from services.auth_service import COOKIE_NAME, AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
@inject
async def login(
    payload: LoginRequest,
    response: Response,
    db: SessionDep,
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
) -> LoginResponse:
    """Authenticate a staff member and start a session.

    Args:
        payload: The submitted username and password.
        response: Used to set the session cookie on success.
        db: The active database session.
        auth_service: Injected service handling credential verification and
            token issuance.

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

    # Secure is always on. Browsers grant http://localhost a secure-context
    # exemption, so this works for the Docker demo without weakening anything.
    # Scope decision (review 2026-08-08): v1 is localhost-only. Reaching the app
    # over a LAN address instead would silently drop this cookie, and fixing that
    # properly means a real cookie-transport setting, deliberately not built yet.
    # Previously this read `not app.debug`, which wrongly tied cookie transport to
    # the verbose-traceback and auto-reload switch.
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=auth_service.token_expiry_hours * 3600,
    )

    return LoginResponse(role=user.role)
