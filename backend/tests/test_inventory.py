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


@pytest.mark.asyncio
async def test_warehouse_manager_can_list_ingredients(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")

    # Act
    response = await client.get("/api/inventory/ingredients")

    # Assert
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cook_can_list_ingredients(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "cook1")

    # Act: Story 2.5 (FR-25) needs Ingredient names to render a Dish's recipe.
    response = await client.get("/api/inventory/ingredients")

    # Assert
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_cannot_list_ingredients(client: AsyncClient) -> None:
    # Act
    response = await client.get("/api/inventory/ingredients")

    # Assert
    assert response.status_code == 401


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
async def test_admin_can_also_log_a_purchase(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.admin, "admin1")
    ingredient = await _create_ingredient(client, "Sugar", current_stock="10.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "3.000"},
    )

    # Assert
    assert response.status_code == 201


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
async def test_negative_adjustment_decreases_current_stock(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Salt", current_stock="10.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "adjustment", "quantity": "-2.500"},
    )

    # Assert
    assert response.status_code == 201
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    assert get_response.json()["current_stock"] == "7.500"


@pytest.mark.asyncio
async def test_positive_adjustment_increases_current_stock(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Pepper", current_stock="10.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "adjustment", "quantity": "2.500"},
    )

    # Assert
    assert response.status_code == 201
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    assert get_response.json()["current_stock"] == "12.500"


@pytest.mark.asyncio
async def test_waste_can_drive_current_stock_negative_not_floor_capped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Cream", current_stock="2.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "waste", "quantity": "5.000"},
    )

    # Assert: exact negative value, not merely "did not error" (AC2/AD-16, a floor-capped
    # implementation would also return 200 and could pass a weaker "no error" assertion).
    assert response.status_code == 201
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    assert get_response.json()["current_stock"] == "-3.000"


@pytest.mark.asyncio
async def test_negative_adjustment_can_drive_current_stock_negative_not_floor_capped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Yeast", current_stock="2.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "adjustment", "quantity": "-5.000"},
    )

    # Assert
    assert response.status_code == 201
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    assert get_response.json()["current_stock"] == "-3.000"


@pytest.mark.asyncio
async def test_purchase_is_recorded_in_the_audit_trail(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    actor = await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Vinegar", current_stock="10.000")

    # Act
    await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "5.000", "notes": "restock from supplier"},
    )
    response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}/movements")

    # Assert
    assert response.status_code == 200
    movements = response.json()
    assert len(movements) == 1
    movement = movements[0]
    assert movement["movement_type"] == "purchase"
    assert movement["quantity_change"] == "5.000"
    assert movement["notes"] == "restock from supplier"
    assert movement["performed_by"] == actor.id


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
    # magnitude submitted (NFR-4).
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
async def test_zero_quantity_for_adjustment_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Onion")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "adjustment", "quantity": "0"},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_non_positive_quantity_for_purchase_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Carrot")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "-1.000"},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_non_positive_quantity_for_waste_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Celery")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "waste", "quantity": "0"},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_quantity_exceeding_the_column_precision_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Leek")

    # Act: the stock_movements.quantity_change column is Numeric(10, 3), so this value has
    # more total digits than the column allows. Verified against a live Postgres, per the
    # Testing section's standing rule, not just reasoned about the Pydantic bound.
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "12345678901.123"},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_logging_a_movement_against_a_nonexistent_ingredient_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")

    # Act
    response = await client.post(
        "/api/inventory/ingredients/999999/movements",
        json={"movement_type": "purchase", "quantity": "1.000"},
    )

    # Assert
    assert response.status_code == 404


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
async def test_waiter_cannot_log_a_movement(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Chili")
    await _login_as(client, db_session, UserRole.waiter, "waiter1")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "1.000"},
    )

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_cannot_log_a_movement(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Paprika")
    # No login for the actual request below; simulate a fresh unauthenticated client by
    # clearing cookies.
    client.cookies.clear()

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "1.000"},
    )

    # Assert
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_single_ingredient_returns_200_for_existing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Thyme")

    # Act
    response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")

    # Assert
    assert response.status_code == 200
    assert response.json()["id"] == ingredient["id"]


@pytest.mark.asyncio
async def test_get_single_ingredient_returns_404_for_nonexistent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")

    # Act
    response = await client.get("/api/inventory/ingredients/999999")

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_movements_returns_empty_list_for_ingredient_with_no_movements(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Cinnamon")

    # Act
    response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}/movements")

    # Assert
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_movements_returns_newest_first(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Nutmeg")
    await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "1.000", "notes": "first"},
    )
    await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "2.000", "notes": "second"},
    )

    # Act
    response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}/movements")

    # Assert
    movements = response.json()
    assert len(movements) == 2
    assert movements[0]["notes"] == "second"
    assert movements[1]["notes"] == "first"


@pytest.mark.asyncio
async def test_cook_can_read_a_single_ingredient_and_its_movement_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Clove")
    await _login_as(client, db_session, UserRole.cook, "cook1")

    # Act
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    movements_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}/movements")

    # Assert
    assert get_response.status_code == 200
    assert movements_response.status_code == 200


@pytest.mark.asyncio
async def test_waiter_cannot_read_a_single_ingredient_or_its_movement_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Bay Leaf")
    await _login_as(client, db_session, UserRole.waiter, "waiter1")

    # Act
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    movements_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}/movements")

    # Assert
    assert get_response.status_code == 403
    assert movements_response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_requests_to_get_routes_are_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Turmeric")
    client.cookies.clear()

    # Act
    get_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}")
    movements_response = await client.get(f"/api/inventory/ingredients/{ingredient['id']}/movements")

    # Assert
    assert get_response.status_code == 401
    assert movements_response.status_code == 401


@pytest.mark.asyncio
async def test_omitting_notes_on_a_movement_defaults_to_null(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Cumin")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "1.000"},
    )

    # Assert
    assert response.status_code == 201
    assert response.json()["notes"] is None


@pytest.mark.asyncio
async def test_alerts_is_empty_when_nothing_is_in_shortage(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    await _create_ingredient(client, "Rice", current_stock="10.000", min_stock_threshold="1.000")

    # Act
    response = await client.get("/api/inventory/alerts")

    # Assert
    assert response.status_code == 200
    assert response.json() == []


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
async def test_a_negative_adjustment_that_crosses_below_threshold_appears_in_alerts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Oregano", current_stock="5.000", min_stock_threshold="3.000")

    # Act
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "adjustment", "quantity": "-3.000"},
    )
    alerts_response = await client.get("/api/inventory/alerts")

    # Assert
    assert response.status_code == 201
    alerts = alerts_response.json()
    assert len(alerts) == 1
    assert alerts[0]["id"] == ingredient["id"]


@pytest.mark.asyncio
async def test_an_ingredient_exactly_at_threshold_is_not_in_shortage(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Thyme", current_stock="5.000", min_stock_threshold="3.000")

    # Act: lands exactly at threshold, not below it.
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "waste", "quantity": "2.000"},
    )
    alerts_response = await client.get("/api/inventory/alerts")

    # Assert
    assert response.status_code == 201
    assert alerts_response.json() == []


@pytest.mark.asyncio
async def test_a_second_waste_movement_while_already_in_shortage_does_not_duplicate_the_alert(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Paprika", current_stock="5.000", min_stock_threshold="3.000")
    first = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "waste", "quantity": "3.000"},
    )
    assert first.status_code == 201

    # Act: already below threshold, this movement drives it further below, not across.
    second = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "waste", "quantity": "1.000"},
    )
    alerts_response = await client.get("/api/inventory/alerts")

    # Assert: still exactly one alert row for this ingredient, not two.
    assert second.status_code == 201
    alerts = [a for a in alerts_response.json() if a["id"] == ingredient["id"]]
    assert len(alerts) == 1
    assert alerts[0]["current_stock"] == "1.000"


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


@pytest.mark.asyncio
async def test_a_purchase_landing_exactly_at_threshold_also_clears_the_alert(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    ingredient = await _create_ingredient(client, "Nutmeg", current_stock="1.000", min_stock_threshold="3.000")

    # Act: lands exactly at threshold.
    response = await client.post(
        f"/api/inventory/ingredients/{ingredient['id']}/movements",
        json={"movement_type": "purchase", "quantity": "2.000"},
    )
    alerts_response = await client.get("/api/inventory/alerts")

    # Assert
    assert response.status_code == 201
    alerts = [a for a in alerts_response.json() if a["id"] == ingredient["id"]]
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_admin_can_read_alerts(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.admin, "admin1")

    # Act
    response = await client.get("/api/inventory/alerts")

    # Assert
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cook_can_read_alerts(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/inventory/alerts")

    # Assert
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_waiter_cannot_read_alerts(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.waiter, "maya")

    # Act
    response = await client.get("/api/inventory/alerts")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_read_alerts(client: AsyncClient) -> None:
    # Act
    response = await client.get("/api/inventory/alerts")

    # Assert
    assert response.status_code == 401
