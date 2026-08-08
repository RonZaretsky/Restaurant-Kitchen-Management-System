from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.cors import CORSMiddleware

from data_models import MAX_PASSWORD_BYTES, User, UserRole
from exceptions import NotAuthenticatedError, SessionExpiredError
from main import app
from services.auth_service import AuthService
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
async def test_login_does_not_return_the_token_in_the_body(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _create_user(db_session, username="waiter_no_token_body")

    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "waiter_no_token_body", "password": _PASSWORD}
    )

    # Assert
    assert response.json() == {"role": "waiter"}
    assert response.cookies["access_token"] not in response.text


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
async def test_overlong_password_is_rejected_identically_for_known_and_unknown_users(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    # bcrypt refuses anything past 72 bytes. If that raise is unguarded, an existing
    # user 500s while an unknown one 401s, and the status code alone enumerates
    # valid usernames.
    await _create_user(db_session, username="waiter_overlong")
    overlong = "a" * (MAX_PASSWORD_BYTES + 30)

    # Act
    known = await client.post(
        "/api/auth/login", json={"username": "waiter_overlong", "password": overlong}
    )
    unknown = await client.post(
        "/api/auth/login", json={"username": "no-such-user", "password": overlong}
    )

    # Assert
    assert known.status_code == unknown.status_code
    assert known.json() == unknown.json()
    assert known.status_code != 500


@pytest.mark.asyncio
async def test_corrupt_stored_hash_fails_closed_rather_than_erroring(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    user = User(
        username="waiter_corrupt_hash",
        password_hash="not-a-bcrypt-hash",
        full_name="Test User",
        role=UserRole.waiter,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "waiter_corrupt_hash", "password": _PASSWORD}
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
async def test_login_token_expiry_matches_configured_lifetime(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _create_user(db_session, username="waiter_expiry")
    configured_hours = int(load_config(SETTINGS.CONFIG_PATH)["auth"]["token_expiry_hours"])

    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "waiter_expiry", "password": _PASSWORD}
    )

    # Assert
    payload = jwt.decode(response.cookies["access_token"], options={"verify_signature": False})
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    expected = datetime.now(timezone.utc) + timedelta(hours=configured_hours)
    assert abs((expires_at - expected).total_seconds()) < 60


@pytest.mark.asyncio
async def test_configured_token_lifetime_is_the_eight_hour_shift() -> None:
    # Arrange / Act
    configured_hours = int(load_config(SETTINGS.CONFIG_PATH)["auth"]["token_expiry_hours"])

    # Assert
    # AD-3 fixes 8 hours as an invariant, a work shift, not a free-tuning knob.
    assert configured_hours == 8


@pytest.mark.asyncio
async def test_service_rejects_a_nonsense_expiry_setting() -> None:
    # Act / Assert
    # Config values arrive as raw strings, so a typo must fail loudly at construction
    # rather than becoming a TypeError deep inside token issuance.
    with pytest.raises(ValueError):
        _build_service(token_expiry_hours="8h")
    with pytest.raises(ValueError):
        _build_service(token_expiry_hours=0)


@pytest.mark.asyncio
async def test_get_current_user_raises_without_a_token(db_session: AsyncSession) -> None:
    # Arrange
    auth_service = _build_service()

    # Act / Assert
    with pytest.raises(NotAuthenticatedError):
        await auth_service.get_current_user(None, db_session)


@pytest.mark.asyncio
async def test_get_current_user_reports_an_expired_session_distinctly(db_session: AsyncSession) -> None:
    # Arrange
    auth_service = _build_service()
    user = await _create_user(db_session, username="waiter_expired")
    expired_token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        _TEST_SECRET,
        algorithm="HS256",
    )

    # Act / Assert
    # An ended shift must not be reported as a bad password, or Story 1.4 shows the
    # wrong message on every timeout.
    with pytest.raises(SessionExpiredError):
        await auth_service.get_current_user(expired_token, db_session)


@pytest.mark.asyncio
async def test_get_current_user_rejects_a_token_without_an_expiry(db_session: AsyncSession) -> None:
    # Arrange
    auth_service = _build_service()
    user = await _create_user(db_session, username="waiter_no_exp")
    # PyJWT only checks exp when the claim is present, so a token omitting it would
    # otherwise be a session that never ends.
    token_without_exp = jwt.encode({"sub": str(user.id)}, _TEST_SECRET, algorithm="HS256")

    # Act / Assert
    with pytest.raises(NotAuthenticatedError):
        await auth_service.get_current_user(token_without_exp, db_session)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_sub", [None, "not-an-int"])
async def test_get_current_user_rejects_a_malformed_subject_claim(
    db_session: AsyncSession, bad_sub: str | None
) -> None:
    # Arrange
    auth_service = _build_service()
    claims: dict = {"exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    if bad_sub is not None:
        claims["sub"] = bad_sub
    token = jwt.encode(claims, _TEST_SECRET, algorithm="HS256")

    # Act / Assert
    # Validly signed but nonsense claims must be a 401, not an unhandled 500.
    with pytest.raises(NotAuthenticatedError):
        await auth_service.get_current_user(token, db_session)


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
async def test_get_current_user_rejects_a_user_deactivated_after_signing_in(
    db_session: AsyncSession,
) -> None:
    # Arrange
    auth_service = _build_service()
    user = await _create_user(db_session, username="waiter_deactivated_later")
    token = auth_service.create_access_token(user)
    user.is_active = False
    await db_session.commit()

    # Act / Assert
    with pytest.raises(NotAuthenticatedError):
        await auth_service.get_current_user(token, db_session)


@pytest.mark.asyncio
async def test_get_current_user_resolves_a_valid_token(db_session: AsyncSession) -> None:
    # Arrange
    auth_service = _build_service()
    user = await _create_user(db_session, username="waiter_valid_token")
    token = auth_service.create_access_token(user)

    # Act
    resolved_user = await auth_service.get_current_user(token, db_session)

    # Assert
    assert resolved_user.id == user.id
    assert resolved_user.username == "waiter_valid_token"


@pytest.mark.asyncio
async def test_current_user_dependency_is_wired_and_usable() -> None:
    # Arrange / Act
    from api.dependencies import CurrentUserDep, get_current_user

    # Assert
    # AD-3 requires one shared dependency rather than per-route reimplementation, so
    # the seam itself has to exist and be Depends-shaped.
    assert CurrentUserDep is not None
    assert callable(get_current_user)


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
