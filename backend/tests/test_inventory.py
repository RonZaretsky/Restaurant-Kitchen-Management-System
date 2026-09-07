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
async def test_admin_can_list_ingredients(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.admin, "admin1")
    create_response = await client.post(
        "/api/inventory/ingredients",
        json={"name": "Rosemary", "unit": "kg", "min_stock_threshold": "1.0"},
    )

    # Act
    response = await client.get("/api/inventory/ingredients")

    # Assert
    assert response.status_code == 200
    assert any(i["id"] == create_response.json()["id"] for i in response.json())


async def _create_ingredient(
    client: AsyncClient, name: str, current_stock: str = "10.0", min_stock_threshold: str = "1.0"
) -> dict:
    response = await client.post(
        "/api/inventory/ingredients",
        json={
            "name": name,
            "unit": "kg",
            "min_stock_threshold": min_stock_threshold,
            "current_stock": current_stock,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_purchase_increases_current_stock(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Flour", current_stock="10.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "5.000"},
    )

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["movement_type"] == "purchase"
    assert body["quantity_change"] == "5.000"
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    assert get_response.json()["current_stock"] == "15.000"


@pytest.mark.asyncio
async def test_waste_decreases_current_stock(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Butter", current_stock="10.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "waste", "quantity": "4.000"},
    )

    # Assert
    assert response.status_code == 201
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    assert get_response.json()["current_stock"] == "6.000"


@pytest.mark.asyncio
async def test_waste_that_would_drive_current_stock_negative_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: a waste movement larger than the stock on hand is rejected cleanly,
    # rather than applied in full and driving current_stock past zero.
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Cream", current_stock="2.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "waste", "quantity": "5.000"},
    )

    # Assert: rejected, current_stock unchanged, no StockMovement row inserted.
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, this movement would drive current stock below zero"
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    assert get_response.json()["current_stock"] == "2.000"
    movements_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}/movements")
    assert movements_response.json() == []


@pytest.mark.asyncio
async def test_waste_quantity_change_is_stored_negative_in_the_audit_trail(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Cheese", current_stock="10.000")

    # Act
    await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "waste", "quantity": "4.000"},
    )
    response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}/movements")

    # Assert: the appended row reflects the actual signed delta applied, not the positive
    # magnitude submitted.
    movements = response.json()
    assert movements[0]["quantity_change"] == "-4.000"


@pytest.mark.asyncio
async def test_consumption_movement_type_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Garlic")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "consumption", "quantity": "1.000"},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cook_cannot_log_a_movement(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Ginger")
    await _login_as(client, db_session, UserRole.cook, "cook1")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "1.000"},
    )

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_waste_movement_that_crosses_below_threshold_appears_in_alerts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Basil", current_stock="5.000", min_stock_threshold="3.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "waste", "quantity": "3.000"},
    )
    alerts_response = await client.get("/api/inventory/alerts")

    # Assert
    assert response.status_code == 201
    alerts = alerts_response.json()
    assert len(alerts) == 1
    assert alerts[0]["id"] == ingredient["id"]
    assert alerts[0]["current_stock"] == "2.000"


@pytest.mark.asyncio
async def test_a_purchase_that_brings_stock_back_above_threshold_clears_the_alert(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Cinnamon", current_stock="1.000", min_stock_threshold="3.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "5.000"},
    )
    alerts_response = await client.get("/api/inventory/alerts")

    # Assert
    assert response.status_code == 201
    alerts = [a for a in alerts_response.json() if a["id"] == ingredient["id"]]
    assert len(alerts) == 0


# --- Soft-deactivate Ingredients --------------------------------------------------------------


@pytest.mark.asyncio
async def test_warehouse_manager_can_deactivate_and_reactivate_an_ingredient(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Fennel")

    # Act
    deactivate_response = await client.post(f"/api/inventory/ingredients/{ingredient['id']}/deactivate")

    # Assert
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    assert get_response.json()["is_active"] is False

    # Act: reactivate
    reactivate_response = await client.post(f"/api/inventory/ingredients/{ingredient['id']}/reactivate")

    # Assert
    assert reactivate_response.status_code == 200
    assert reactivate_response.json()["is_active"] is True


@pytest.mark.asyncio
async def test_a_new_stock_movement_against_a_deactivated_ingredient_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: a new Stock Movement is blocked against a deactivated Ingredient.
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Tarragon", current_stock="5.000")
    deactivate_response = await client.post(f"/api/inventory/ingredients/{ingredient['id']}/deactivate")
    assert deactivate_response.status_code == 200

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "1.000"},
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, ingredient is deactivated"
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    assert get_response.json()["current_stock"] == "5.000"
