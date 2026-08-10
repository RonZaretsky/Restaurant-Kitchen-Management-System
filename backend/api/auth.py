from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from api.dependencies import CurrentUserDep
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import LoginRequest, LoginResponse, User, UserResponse
from services.auth_service import COOKIE_NAME, AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])

_ME_ERROR_DESCRIPTIONS = {401: "No valid session cookie was supplied"}


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


@router.get(
    "/me",
    response_model=UserResponse,
    responses=error_responses(_ME_ERROR_DESCRIPTIONS, 401),
)
async def get_own_profile(user: CurrentUserDep) -> User:
    """Return the authenticated User's own profile.

    The frontend's only way to learn who is logged in and what Role they
    hold after a page reload, since the session cookie is httpOnly and
    unreadable by JavaScript (AD-3).

    Args:
        user: The authenticated User, resolved by the shared CurrentUserDep
            seam.

    Returns:
        The caller's own User record.

    Raises:
        NotAuthenticatedError: Propagated from get_current_user, handled
            globally as a 401, if no valid session cookie is present.
        SessionExpiredError: Same handling, if the cookie's token has
            expired.
    """
    return user
