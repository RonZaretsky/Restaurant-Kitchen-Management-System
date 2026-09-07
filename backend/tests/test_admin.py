
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import User, UserRole
from services.auth_service import AuthService

_PASSWORD = "correct-horse-battery-staple"


async def _create_user(
    db_session: AsyncSession,
    username: str,
    password: str = _PASSWORD,
    role: UserRole = UserRole.waiter,
    is_active: bool = True,
) -> User:
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


async def _login(client: AsyncClient, username: str, password: str = _PASSWORD) -> None:
    # AsyncClient persists cookies across calls, so every subsequent request on this
    # client instance carries the session started here.
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


async def _login_as_admin(client: AsyncClient, db_session: AsyncSession, username: str = "admin1") -> User:
    admin = await _create_user(db_session, username=username, role=UserRole.admin)
    await _login(client, username)
    return admin


async def _read_row(db_session: AsyncSession, user_id: int) -> dict:
    # db_session is built with expire_on_commit=False and holds the seeded User in its
    # identity map, so a plain select() hands back the stale in-memory object and any
    # assertion on it is vacuous. Raw SQL bypasses the identity map entirely and reads
    # what the app's own connection actually committed.
    result = await db_session.execute(
        text("SELECT username, full_name, role, is_active, password_hash FROM users WHERE id = :id"),
        {"id": user_id},
    )
    row = result.mappings().one()
    return dict(row)


@pytest.mark.asyncio
async def test_create_user_succeeds_and_new_user_can_login_immediately(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    create_response = await client.post(
        "/api/admin/users",
        json={
            "username": "new_cook",
            "full_name": "New Cook",
            "role": "cook",
            "password": "a-fresh-password",
        },
    )

    # Assert
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["username"] == "new_cook"
    assert body["role"] == "cook"
    assert body["is_active"] is True

    login_client_response = await client.post(
        "/api/auth/login", json={"username": "new_cook", "password": "a-fresh-password"}
    )
    assert login_client_response.status_code == 200
    assert login_client_response.json() == {"role": "cook"}


@pytest.mark.asyncio
async def test_created_user_password_is_hashed_and_never_returned(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.post(
        "/api/admin/users",
        json={
            "username": "hash_check",
            "full_name": "Hash Check",
            "role": "waiter",
            "password": "some-plaintext-password",
        },
    )

    # Assert
    assert "password_hash" not in response.json()
    assert "some-plaintext-password" not in response.text

    result = await db_session.execute(select(User).where(User.username == "hash_check"))
    stored = result.scalar_one()
    assert stored.password_hash.startswith("$2b$")
    assert stored.password_hash != "some-plaintext-password"


@pytest.mark.asyncio
async def test_create_user_duplicate_username_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    payload = {"username": "dupe_user", "full_name": "Dupe", "role": "waiter", "password": _PASSWORD}
    first = await client.post("/api/admin/users", json=payload)
    assert first.status_code == 201

    # Act
    second = await client.post("/api/admin/users", json=payload)

    # Assert
    assert second.status_code == 409
    assert second.json() == {"detail": "That username already exists"}


@pytest.mark.asyncio
async def test_deactivate_blocks_login_but_keeps_the_row(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    target = await _create_user(db_session, username="to_deactivate")

    # Act
    response = await client.post(f"/api/admin/users/{target.id}/deactivate")

    # Assert
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    login_response = await client.post(
        "/api/auth/login", json={"username": "to_deactivate", "password": _PASSWORD}
    )
    assert login_response.status_code == 401

    result = await db_session.execute(select(User).where(User.id == target.id))
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_reactivate_restores_login(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    target = await _create_user(db_session, username="to_reactivate", is_active=False)

    # Act
    response = await client.post(f"/api/admin/users/{target.id}/reactivate")

    # Assert
    assert response.status_code == 200
    assert response.json()["is_active"] is True

    login_response = await client.post(
        "/api/auth/login", json={"username": "to_reactivate", "password": _PASSWORD}
    )
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_overwrites_hash_and_never_needs_the_old_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    target = await _create_user(db_session, username="reset_target", password="old-password")

    # Act
    response = await client.post(
        f"/api/admin/users/{target.id}/reset-password", json={"new_password": "brand-new-password"}
    )

    # Assert
    assert response.status_code == 200

    old_login = await client.post(
        "/api/auth/login", json={"username": "reset_target", "password": "old-password"}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/auth/login", json={"username": "reset_target", "password": "brand-new-password"}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_last_admin_lockout_on_deactivate(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    admin = await _login_as_admin(client, db_session, username="sole_admin")

    # Act
    response = await client.post(f"/api/admin/users/{admin.id}/deactivate")

    # Assert
    assert response.status_code == 409
    assert response.json() == {"detail": "Rejected, at least one admin must stay active"}

    # Read past the identity map: asserting on a select() here would pass even if the
    # admin really had been deactivated.
    assert (await _read_row(db_session, admin.id))["is_active"] is True


@pytest.mark.asyncio
async def test_last_admin_lockout_on_demote(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    admin = await _login_as_admin(client, db_session, username="sole_admin_demote")

    # Act
    response = await client.patch(f"/api/admin/users/{admin.id}", json={"role": "waiter"})

    # Assert
    assert response.status_code == 409
    assert response.json() == {"detail": "Rejected, at least one admin must stay active"}

    assert (await _read_row(db_session, admin.id))["role"] == "admin"


@pytest.mark.asyncio
async def test_last_admin_lockout_does_not_trip_with_a_second_active_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    admin_one = await _login_as_admin(client, db_session, username="admin_one")
    await _create_user(db_session, username="admin_two", role=UserRole.admin)

    # Act
    response = await client.post(f"/api/admin/users/{admin_one.id}/deactivate")

    # Assert
    assert response.status_code == 200
    assert response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_update_user_edits_full_name_and_role(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    target = await _create_user(db_session, username="editable_user", role=UserRole.waiter)

    # Act
    response = await client.patch(
        f"/api/admin/users/{target.id}", json={"full_name": "Renamed", "role": "cook"}
    )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Renamed"
    assert body["role"] == "cook"


@pytest.mark.asyncio
async def test_update_user_requires_at_least_one_field(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    target = await _create_user(db_session, username="no_op_edit")

    # Act
    response = await client.patch(f"/api/admin/users/{target.id}", json={})

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_users_returns_created_accounts(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session, username="lister_admin")
    await _create_user(db_session, username="listed_user")

    # Act
    response = await client.get("/api/admin/users")

    # Assert
    assert response.status_code == 200
    usernames = {row["username"] for row in response.json()}
    assert {"lister_admin", "listed_user"}.issubset(usernames)


# Every route in api/admin.py, so the authorization tests below cover the whole
# router rather than one representative route. A new route added without
# AdminDep must fail these.
_ADMIN_ROUTES = [
    ("post", "/api/admin/users", {"username": "x", "full_name": "X", "role": "waiter", "password": "pw"}),
    ("get", "/api/admin/users", None),
    ("get", "/api/admin/users/1", None),
    ("patch", "/api/admin/users/1", {"full_name": "X"}),
    ("post", "/api/admin/users/1/deactivate", None),
    ("post", "/api/admin/users/1/reactivate", None),
    ("post", "/api/admin/users/1/reset-password", {"new_password": "pw"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.waiter, UserRole.cook, UserRole.warehouse_manager])
@pytest.mark.parametrize("method,path,body", _ADMIN_ROUTES)
async def test_every_admin_route_returns_403_to_a_non_admin(
    client: AsyncClient, db_session: AsyncSession, role: UserRole, method: str, path: str, body: dict | None
) -> None:
    # Arrange
    await _create_user(db_session, username=f"non_admin_{role.value}", role=role)
    await _login(client, f"non_admin_{role.value}")

    # Act
    response = await getattr(client, method)(path, **({"json": body} if body else {}))

    # Assert
    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission to perform this action"}


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", _ADMIN_ROUTES)
async def test_every_admin_route_returns_401_to_an_unauthenticated_caller(
    client: AsyncClient, method: str, path: str, body: dict | None
) -> None:
    # Act
    response = await getattr(client, method)(path, **({"json": body} if body else {}))

    # Assert
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_username_is_case_insensitive(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    first = await client.post(
        "/api/admin/users",
        json={"username": "Casey", "full_name": "Casey", "role": "cook", "password": _PASSWORD},
    )
    assert first.status_code == 201

    # Act
    second = await client.post(
        "/api/admin/users",
        json={"username": "casey", "full_name": "Other Casey", "role": "waiter", "password": _PASSWORD},
    )

    # Assert
    assert second.status_code == 409
    assert second.json() == {"detail": "That username already exists"}

