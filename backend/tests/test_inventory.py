import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import User, UserRole
from services.auth_service import AuthService

_PASSWORD = "correct-horse-battery-staple"


async def _create_user(db_session: AsyncSession, username: str, role: UserRole) -> User:
    user = User(
        username=username,
        password_hash=AuthService.hash_password(_PASSWORD),
        full_name="Test User",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _login(client: AsyncClient, username: str) -> None:
    response = await client.post("/api/auth/login", json={"username": username, "password": _PASSWORD})
    assert response.status_code == 200


async def _login_as(client: AsyncClient, db_session: AsyncSession, role: UserRole, username: str) -> User:
    user = await _create_user(db_session, username=username, role=role)
    await _login(client, username)
    return user


@pytest.mark.asyncio
async def test_warehouse_manager_can_create_an_ingredient(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")

    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Tomato", "unit": "kg", "min_stock_threshold": "5.0", "current_stock": "10.0"},
    )

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Tomato"
    assert body["unit"] == "kg"
    assert body["current_stock"] == "10.000"
    assert body["min_stock_threshold"] == "5.000"


@pytest.mark.asyncio
async def test_admin_can_also_create_an_ingredient(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.admin, "admin1")

    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Basil", "unit": "kg", "min_stock_threshold": "0.5"},
    )

    # Assert
    assert response.status_code == 201
    assert response.json()["name"] == "Basil"


@pytest.mark.asyncio
async def test_omitting_current_stock_defaults_to_zero(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")

    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Olive Oil", "unit": "liter", "min_stock_threshold": "2.0"},
    )

    # Assert
    assert response.status_code == 201
    assert response.json()["current_stock"] == "0.000"


@pytest.mark.asyncio
async def test_duplicate_name_same_case_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    await client.post(
        "/api/inventory/ingredients",
        json={"name": "Mozzarella", "unit": "kg", "min_stock_threshold": "1.0"},
    )

    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Mozzarella", "unit": "kg", "min_stock_threshold": "1.0"},
    )

    # Assert
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_duplicate_name_different_case_is_also_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    await client.post(
        "/api/inventory/ingredients",
        json={"name": "Tomato", "unit": "kg", "min_stock_threshold": "1.0"},
    )

    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "tomato", "unit": "kg", "min_stock_threshold": "1.0"},
    )

    # Assert
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_cook_cannot_create_an_ingredient(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "cook1")

    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Zucchini", "unit": "kg", "min_stock_threshold": "1.0"},
    )

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_waiter_cannot_create_an_ingredient(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.waiter, "waiter1")

    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Salmon", "unit": "kg", "min_stock_threshold": "1.0"},
    )

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_is_rejected(client: AsyncClient) -> None:
    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Parmesan", "unit": "kg", "min_stock_threshold": "1.0"},
    )

    # Assert
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_negative_min_stock_threshold_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")

    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Pancetta", "unit": "kg", "min_stock_threshold": "-1.0"},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_negative_current_stock_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")

    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Espresso", "unit": "kg", "min_stock_threshold": "1.0", "current_stock": "-2.0"},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_min_stock_threshold_exceeding_the_column_precision_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")

    # Act: the ingredients.min_stock_threshold column is Numeric(10, 3), so this value
    # has more total digits than the column allows. Without a matching Pydantic bound,
    # this reaches the database and raises an unhandled asyncpg.NumericValueOutOfRangeError
    # (a 500) instead of a clean 422.
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Overflow", "unit": "kg", "min_stock_threshold": "12345678901.123"},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_blank_name_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")

    # Act
    response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "   ", "unit": "kg", "min_stock_threshold": "1.0"},
    )

    # Assert
    assert response.status_code == 422
