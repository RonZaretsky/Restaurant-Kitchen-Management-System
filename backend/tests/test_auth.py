from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.cors import CORSMiddleware

from data_models import User, UserRole
from exceptions import NotAuthenticatedError
from main import app
from services.auth_service import COOKIE_NAME, AuthService
from utils import load_config
from constants import SETTINGS

_PASSWORD = "correct-horse-battery-staple"
_TEST_SECRET = "test-secret-key-that-is-at-least-32-bytes-long"


def _build_service(secret_key: str = _TEST_SECRET, token_expiry_hours: int = 8) -> AuthService:
    return AuthService(secret_key=secret_key, token_expiry_hours=token_expiry_hours, logger=logger)


async def _create_user(
    db_session: AsyncSession,
    username: str = "waiter1",
    password: str = _PASSWORD,
    role: UserRole = UserRole.waiter,
    is_active: bool = True,
) -> User:
    # Arrange helper: hashes through the service's own seam, so account creation and
    # login can never diverge on cost or salt settings.
    user = User(
        username=username,
        password_hash=AuthService.hash_password(password),
        full_name="Test User",
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_login_success_sets_cookie_and_returns_role(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _create_user(db_session, username="waiter_success", role=UserRole.waiter)

    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "waiter_success", "password": _PASSWORD}
    )

    # Assert
    assert response.status_code == 200
    assert response.json() == {"role": "waiter"}
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_login_cookie_carries_every_required_attribute(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _create_user(db_session, username="waiter_cookie_attrs")

    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "waiter_cookie_attrs", "password": _PASSWORD}
    )

    # Assert
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert f"Max-Age={8 * 3600}" in set_cookie


@pytest.mark.asyncio
async def test_login_wrong_password_rejected_with_generic_message(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _create_user(db_session, username="waiter_wrong_pw")

    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "waiter_wrong_pw", "password": "not-the-password"}
    )

    # Assert
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


@pytest.mark.asyncio
async def test_login_wrong_username_rejected_with_same_message(client: AsyncClient) -> None:
    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "no-such-user", "password": _PASSWORD}
    )

    # Assert
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


@pytest.mark.asyncio
async def test_login_deactivated_user_rejected_with_same_message(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _create_user(db_session, username="deactivated_user", is_active=False)

    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "deactivated_user", "password": _PASSWORD}
    )

    # Assert
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


@pytest.mark.asyncio
async def test_configured_token_lifetime_is_the_eight_hour_shift() -> None:
    # Arrange / Act
    configured_hours = int(load_config(SETTINGS.CONFIG_PATH)["auth"]["token_expiry_hours"])

    # Assert
    # AD-3 fixes 8 hours as an invariant, a work shift, not a free-tuning knob.
    assert configured_hours == 8


@pytest.mark.asyncio
async def test_me_returns_the_authenticated_users_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _create_user(db_session, username="waiter_me", role=UserRole.waiter)
    await client.post("/api/auth/login", json={"username": "waiter_me", "password": _PASSWORD})

    # Act
    response = await client.get("/api/auth/me")

    # Assert
    body = response.json()
    assert response.status_code == 200
    assert body["username"] == "waiter_me"
    assert body["role"] == "waiter"
    assert body["is_active"] is True
    assert "password_hash" not in body
    assert set(body.keys()) == {"id", "username", "full_name", "role", "is_active", "created_at"}


@pytest.mark.asyncio
async def test_me_without_a_session_is_rejected(client: AsyncClient) -> None:
    # Act
    response = await client.get("/api/auth/me")

    # Assert
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_me_rejects_a_valid_cookie_whose_account_was_deactivated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    # Mid-session deactivation is the whole reason /me is re-read rather than the
    # frontend caching the login response, so the route, not just the service, has
    # to reject it.
    user = await _create_user(db_session, username="waiter_me_deactivated")
    await client.post(
        "/api/auth/login", json={"username": "waiter_me_deactivated", "password": _PASSWORD}
    )
    user.is_active = False
    await db_session.commit()

    # Act
    response = await client.get("/api/auth/me")

    # Assert
    assert response.status_code == 401
    assert "password_hash" not in response.text


@pytest.mark.asyncio
async def test_me_rejects_an_expired_session_cookie(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    # AD-3 has no refresh flow, so an ended shift must surface as a plain 401 at the
    # route the shell polls, not as a 500 out of token decoding.
    user = await _create_user(db_session, username="waiter_me_expired")
    secret_key = load_config(SETTINGS.CONFIG_PATH)["auth"]["secret_key"]
    expired_token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        secret_key,
        algorithm="HS256",
    )
    client.cookies.set(COOKIE_NAME, expired_token)

    # Act
    response = await client.get("/api/auth/me")

    # Assert
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_the_session_cookie(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _create_user(db_session, username="waiter_logout")
    await client.post("/api/auth/login", json={"username": "waiter_logout", "password": _PASSWORD})

    # Act
    response = await client.post("/api/auth/logout")

    # Assert
    assert response.status_code == 204
    set_cookie = response.headers["set-cookie"]
    assert f"{COOKIE_NAME}=" in set_cookie
    assert "Max-Age=0" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie


@pytest.mark.asyncio
async def test_get_current_user_rejects_a_token_signed_with_another_secret(
    db_session: AsyncSession,
) -> None:
    # Arrange
    auth_service = _build_service()
    user = await _create_user(db_session, username="waiter_wrong_secret")
    forged = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "a-different-secret-that-is-also-at-least-32-bytes",
        algorithm="HS256",
    )

    # Act / Assert
    with pytest.raises(NotAuthenticatedError):
        await auth_service.get_current_user(forged, db_session)


@pytest.mark.asyncio
async def test_cors_allows_exactly_the_configured_origin() -> None:
    # Arrange
    configured_origin = load_config(SETTINGS.CONFIG_PATH)["cors"]["allow_origin"]

    # Act
    cors_middleware = next(m for m in app.user_middleware if m.cls is CORSMiddleware)

    # Assert
    assert cors_middleware.kwargs["allow_origins"] == [configured_origin]
    assert cors_middleware.kwargs["allow_credentials"] is True


@pytest.mark.asyncio
async def test_health_route_stays_public(client: AsyncClient) -> None:
    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
