from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from data_models import User, UserRole
from exceptions import InvalidCredentialsError
from services.auth_service import AuthService

_PASSWORD = "correct-horse-battery-staple"


async def _create_user(
    db_session: AsyncSession,
    username: str = "waiter1",
    password: str = _PASSWORD,
    role: UserRole = UserRole.waiter,
    is_active: bool = True,
) -> User:
    # Arrange helper: hashes the same way AuthService does, so tests exercise a real
    # bcrypt round trip rather than a fake stored hash.
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(
        username=username,
        password_hash=password_hash,
        full_name="Test User",
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _make_request(cookie_header: str | None = None) -> Request:
    headers = []
    if cookie_header is not None:
        headers.append((b"cookie", cookie_header.encode("utf-8")))
    scope = {"type": "http", "headers": headers, "method": "GET", "path": "/"}
    return Request(scope)


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
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie_header


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
async def test_login_failure_never_leaks_plaintext_password(client: AsyncClient) -> None:
    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "no-such-user", "password": "super-secret-plaintext"}
    )

    # Assert
    assert "super-secret-plaintext" not in response.text


@pytest.mark.asyncio
async def test_login_token_expiry_is_eight_hours(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _create_user(db_session, username="waiter_expiry")

    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "waiter_expiry", "password": _PASSWORD}
    )

    # Assert
    token = response.cookies["access_token"]
    payload = jwt.decode(token, options={"verify_signature": False})
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    expected = datetime.now(timezone.utc) + timedelta(hours=8)
    assert abs((expires_at - expected).total_seconds()) < 60


@pytest.mark.asyncio
async def test_get_current_user_raises_without_cookie(db_session: AsyncSession) -> None:
    # Arrange
    auth_service = AuthService(secret_key="test-secret-key-that-is-at-least-32-bytes-long", token_expiry_hours=8)
    request = _make_request(cookie_header=None)

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await auth_service.get_current_user(request, db_session)


@pytest.mark.asyncio
async def test_get_current_user_raises_on_expired_token(db_session: AsyncSession) -> None:
    # Arrange
    auth_service = AuthService(secret_key="test-secret-key-that-is-at-least-32-bytes-long", token_expiry_hours=8)
    user = await _create_user(db_session, username="waiter_expired")
    expired_payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    expired_token = jwt.encode(expired_payload, "test-secret-key-that-is-at-least-32-bytes-long", algorithm="HS256")
    request = _make_request(cookie_header=f"access_token={expired_token}")

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await auth_service.get_current_user(request, db_session)


@pytest.mark.asyncio
async def test_get_current_user_raises_on_wrong_secret(db_session: AsyncSession) -> None:
    # Arrange
    auth_service = AuthService(secret_key="test-secret-key-that-is-at-least-32-bytes-long", token_expiry_hours=8)
    user = await _create_user(db_session, username="waiter_wrong_secret")
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token_signed_with_other_secret = jwt.encode(payload, "a-different-secret-that-is-also-at-least-32-bytes", algorithm="HS256")
    request = _make_request(cookie_header=f"access_token={token_signed_with_other_secret}")

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await auth_service.get_current_user(request, db_session)


@pytest.mark.asyncio
async def test_get_current_user_resolves_valid_token(db_session: AsyncSession) -> None:
    # Arrange
    auth_service = AuthService(secret_key="test-secret-key-that-is-at-least-32-bytes-long", token_expiry_hours=8)
    user = await _create_user(db_session, username="waiter_valid_token")
    token = auth_service.create_access_token(user)
    request = _make_request(cookie_header=f"access_token={token}")

    # Act
    resolved_user = await auth_service.get_current_user(request, db_session)

    # Assert
    assert resolved_user.id == user.id
    assert resolved_user.username == "waiter_valid_token"


@pytest.mark.asyncio
async def test_cors_allow_origin_is_explicit_not_wildcard() -> None:
    # Arrange
    from main import app
    from starlette.middleware.cors import CORSMiddleware

    # Act
    cors_middleware = next(m for m in app.user_middleware if m.cls is CORSMiddleware)

    # Assert
    allowed_origins = cors_middleware.kwargs["allow_origins"]
    assert allowed_origins != ["*"]
    assert len(allowed_origins) >= 1


@pytest.mark.asyncio
async def test_health_route_stays_public(client: AsyncClient) -> None:
    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
