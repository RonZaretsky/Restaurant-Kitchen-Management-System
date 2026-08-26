import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import User, UserRole
from main import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME, _bootstrap_first_admin, app
from services.auth_service import AuthService


@pytest.mark.asyncio
async def test_bootstrap_creates_a_default_admin_when_users_table_is_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: `client`'s own lifespan already ran with BOOTSTRAP_ADMIN=false (conftest.py), so
    # the users table is still empty here - call the bootstrap directly to test it in isolation.

    # Act
    await _bootstrap_first_admin(app)

    # Assert: the default Admin can actually log in, not just that a row exists.
    login_response = await client.post(
        "/api/auth/login", json={"username": DEFAULT_ADMIN_USERNAME, "password": DEFAULT_ADMIN_PASSWORD}
    )
    assert login_response.status_code == 200

    result = await db_session.execute(select(User))
    users = result.scalars().all()
    assert len(users) == 1
    assert users[0].username == DEFAULT_ADMIN_USERNAME
    assert users[0].role == UserRole.admin
    assert users[0].is_active is True


@pytest.mark.asyncio
async def test_bootstrap_is_a_no_op_once_any_user_exists(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: a User already exists, not necessarily an Admin - the bootstrap only cares whether
    # the table is empty, not whether an Admin specifically exists yet.
    user = User(
        username="amir",
        password_hash=AuthService.hash_password("correct-horse-battery-staple"),
        full_name="Amir Cohen",
        role=UserRole.cook,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Act
    await _bootstrap_first_admin(app)

    # Assert: no default Admin was created alongside the existing user.
    result = await db_session.execute(select(User))
    users = result.scalars().all()
    assert len(users) == 1
    assert users[0].username == "amir"


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_across_repeated_calls(client: AsyncClient, db_session: AsyncSession) -> None:
    # Act: the real app startup runs this on every boot, not just the very first.
    await _bootstrap_first_admin(app)
    await _bootstrap_first_admin(app)

    # Assert
    result = await db_session.execute(select(User))
    assert len(result.scalars().all()) == 1
