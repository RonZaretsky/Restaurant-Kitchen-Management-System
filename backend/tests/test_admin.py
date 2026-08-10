import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import User, UserRole
from exceptions import LastAdminLockoutError
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
async def test_create_user_missing_password_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.post(
        "/api/admin/users",
        json={"username": "no_password", "full_name": "No Password", "role": "waiter", "password": ""},
    )

    # Assert
    assert response.status_code == 422

    result = await db_session.execute(select(User).where(User.username == "no_password"))
    assert result.scalar_one_or_none() is None


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
async def test_create_user_duplicate_username_rejected_even_if_deactivated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    await _create_user(db_session, username="dormant_user", is_active=False)

    # Act
    response = await client.post(
        "/api/admin/users",
        json={"username": "dormant_user", "full_name": "Reused Name", "role": "waiter", "password": _PASSWORD},
    )

    # Assert
    assert response.status_code == 409


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
async def test_concurrent_deactivations_cannot_remove_the_last_admin(
    db_session: AsyncSession, migrated_database: str
) -> None:
    # Arrange
    # Two admins, each deactivating the other at the same time. Before the row lock,
    # both guards read a count of one other active admin, both passed, and both
    # committed, leaving zero active admins and locking user management for good.
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from loguru import logger
    from services.user_service import UserService
    from tests.conftest import build_database_url

    first = await _create_user(db_session, username="race_admin_a", role=UserRole.admin)
    second = await _create_user(db_session, username="race_admin_b", role=UserRole.admin)

    engine = create_async_engine(build_database_url(migrated_database))
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    service = UserService(logger=logger)

    async def deactivate(actor_id: int, target_id: int):
        async with factory() as session:
            actor = await session.get(User, actor_id)
            return await service.deactivate_user(session, actor, target_id)

    # Act
    try:
        results = await asyncio.gather(
            deactivate(first.id, second.id),
            deactivate(second.id, first.id),
            return_exceptions=True,
        )

        # Assert
        rejected = [r for r in results if isinstance(r, LastAdminLockoutError)]
        assert len(rejected) == 1, f"exactly one deactivation must be rejected, got {results}"

        remaining = await db_session.execute(
            text("SELECT count(*) FROM users WHERE role = 'admin' AND is_active = true")
        )
        assert remaining.scalar_one() == 1
    finally:
        await engine.dispose()


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
async def test_get_user_404_for_missing_id(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.get("/api/admin/users/999999")

    # Assert
    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


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
async def test_openapi_documents_every_error_status_with_a_body_schema() -> None:
    # Arrange
    from main import app

    # Act
    schema = app.openapi()
    paths = schema["paths"]

    # Assert
    # Story 1.2 deferred this here: ForbiddenError and friends are plain Exceptions,
    # so FastAPI cannot infer them and every status below has to be declared by hand.
    assert "403" in paths["/api/admin/users"]["post"]["responses"]
    assert "409" in paths["/api/admin/users"]["post"]["responses"]
    assert "404" in paths["/api/admin/users/{user_id}"]["get"]["responses"]
    assert "409" in paths["/api/admin/users/{user_id}/deactivate"]["post"]["responses"]

    for path, operations in paths.items():
        if not path.startswith("/api/admin"):
            continue
        for operation in operations.values():
            for status, spec in operation["responses"].items():
                if status == "422":
                    continue
                # A status with no body schema tells a generated client nothing about
                # the `detail` field it will actually receive.
                assert "content" in spec, f"{path} {status} has no body schema"


@pytest.mark.asyncio
async def test_multibyte_password_is_rejected_as_422_not_500(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    # 72 characters but 144 bytes. Pydantic's max_length counts characters while
    # bcrypt's limit is bytes, so this used to sail through validation and then
    # raise ValueError out of the handler as an opaque 500.
    multibyte = "é" * 72

    # Act
    created = await client.post(
        "/api/admin/users",
        json={"username": "multibyte", "full_name": "MB", "role": "waiter", "password": multibyte},
    )
    target = await _create_user(db_session, username="reset_multibyte")
    reset = await client.post(
        f"/api/admin/users/{target.id}/reset-password", json={"new_password": multibyte}
    )

    # Assert
    assert created.status_code == 422
    assert reset.status_code == 422


@pytest.mark.asyncio
async def test_username_and_full_name_are_trimmed(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.post(
        "/api/admin/users",
        json={"username": "  spaced  ", "full_name": "  Spaced Name  ", "role": "cook", "password": _PASSWORD},
    )

    # Assert
    assert response.status_code == 201
    assert response.json()["username"] == "spaced"
    assert response.json()["full_name"] == "Spaced Name"
    # The untrimmed form would be an account nobody could ever type at the login box.
    assert (await client.post("/api/auth/login", json={"username": "spaced", "password": _PASSWORD})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["   ", "\t", ""])
async def test_blank_username_is_rejected(client: AsyncClient, db_session: AsyncSession, blank: str) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.post(
        "/api/admin/users",
        json={"username": blank, "full_name": "Blank", "role": "cook", "password": _PASSWORD},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_blank_full_name_is_rejected_on_update(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    target = await _create_user(db_session, username="blank_name_target")

    # Act
    response = await client.patch(f"/api/admin/users/{target.id}", json={"full_name": "   "})

    # Assert
    assert response.status_code == 422


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


@pytest.mark.asyncio
async def test_login_is_case_insensitive(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    await client.post(
        "/api/admin/users",
        json={"username": "MixedCase", "full_name": "Mixed", "role": "cook", "password": _PASSWORD},
    )

    # Act
    response = await client.post(
        "/api/auth/login", json={"username": "mixedcase", "password": _PASSWORD}
    )

    # Assert
    # Creation rejects case-variants as duplicates, so login has to accept them, or an
    # account created as "MixedCase" would be unreachable and "mixedcase" unclaimable.
    assert response.status_code == 200
    assert response.json() == {"role": "cook"}


@pytest.mark.asyncio
async def test_deactivate_is_idempotent_and_does_not_log_a_second_transition(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    target = await _create_user(db_session, username="idempotent", is_active=False)

    # Act
    response = await client.post(f"/api/admin/users/{target.id}/deactivate")

    # Assert
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert (await _read_row(db_session, target.id))["is_active"] is False


@pytest.mark.asyncio
async def test_reset_password_replaces_the_stored_hash(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    target = await _create_user(db_session, username="hash_rotates", password="old-password")
    before = (await _read_row(db_session, target.id))["password_hash"]

    # Act
    response = await client.post(
        f"/api/admin/users/{target.id}/reset-password", json={"new_password": "new-password"}
    )

    # Assert
    assert response.status_code == 200
    after = (await _read_row(db_session, target.id))["password_hash"]
    assert after != before
    assert after.startswith("$2b$")


@pytest.mark.asyncio
async def test_read_endpoints_never_expose_a_password(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session, username="reader_admin")
    created = await client.post(
        "/api/admin/users",
        json={"username": "exposed", "full_name": "E", "role": "cook", "password": "leaky-plaintext"},
    )
    user_id = created.json()["id"]

    # Act
    listed = await client.get("/api/admin/users")
    fetched = await client.get(f"/api/admin/users/{user_id}")

    # Assert
    for response in (created, listed, fetched):
        assert "password_hash" not in response.text
        assert "leaky-plaintext" not in response.text
        assert "$2b$" not in response.text
