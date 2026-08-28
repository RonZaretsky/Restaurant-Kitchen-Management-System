import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import Ingredient, Order, OrderItem, OrderItemStatus, OrderStatus, Unit, User, UserRole
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


async def _create_table(client: AsyncClient, db_session: AsyncSession, table_number: int) -> dict:
    admin_username = f"table-admin-{table_number}"
    await _create_user(db_session, admin_username, UserRole.admin)
    await _login(client, admin_username)
    response = await client.post("/api/tables", json={"table_number": table_number, "capacity": 4})
    assert response.status_code == 201
    return response.json()


async def _open_table(client: AsyncClient, db_session: AsyncSession, table_number: int) -> tuple[dict, dict]:
    table = await _create_table(client, db_session, table_number)
    await _login_as(client, db_session, UserRole.waiter, f"waiter-{table_number}")
    response = await client.post(f"/api/orders/tables/{table['id']}/open")
    assert response.status_code == 201
    return response.json(), table


async def _create_available_dish(
    client: AsyncClient, db_session: AsyncSession, name: str = "Margherita", price: str = "12.50"
) -> dict:
    await _create_user(db_session, f"dish-admin-{name}", UserRole.admin)
    await _login(client, f"dish-admin-{name}")
    category_response = await client.post("/api/menu/categories", json={"name": f"{name} Category"})
    assert category_response.status_code == 201
    category = category_response.json()
    dish_response = await client.post(
        "/api/menu/dishes",
        json={"name": name, "price": price, "category_id": category["id"], "prep_time_minutes": 15},
    )
    assert dish_response.status_code == 201
    dish = dish_response.json()
    ingredient = Ingredient(name=f"{name} Ingredient", unit=Unit.kg, current_stock=10, min_stock_threshold=1)
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    recipe_response = await client.post(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients",
        json={"ingredient_id": ingredient.id, "quantity": "0.500", "unit": "kg"},
    )
    assert recipe_response.status_code == 201
    available_response = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"is_available": True})
    assert available_response.status_code == 200
    return available_response.json()


async def _add_item(client: AsyncClient, order_id: int, dish_id: int, quantity: int = 1) -> dict:
    response = await client.post(f"/api/orders/{order_id}/items", json={"dish_id": dish_id, "quantity": quantity})
    assert response.status_code == 201
    return response.json()


async def _create_available_dish_with_stock(
    client: AsyncClient, db_session: AsyncSession, name: str, ingredient_stock: str, recipe_quantity: str
) -> dict:
    # Same shape as _create_available_dish, but with a controlled stock/recipe_quantity pair so
    # max_preparable_quantity tests can assert an exact expected value.
    await _create_user(db_session, f"dish-admin-{name}", UserRole.admin)
    await _login(client, f"dish-admin-{name}")
    category_response = await client.post("/api/menu/categories", json={"name": f"{name} Category"})
    assert category_response.status_code == 201
    category = category_response.json()
    dish_response = await client.post(
        "/api/menu/dishes",
        json={"name": name, "price": "12.50", "category_id": category["id"], "prep_time_minutes": 15},
    )
    assert dish_response.status_code == 201
    dish = dish_response.json()
    ingredient = Ingredient(
        name=f"{name} Ingredient", unit=Unit.kg, current_stock=ingredient_stock, min_stock_threshold="1.000"
    )
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    recipe_response = await client.post(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients",
        json={"ingredient_id": ingredient.id, "quantity": recipe_quantity, "unit": "kg"},
    )
    assert recipe_response.status_code == 201
    available_response = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"is_available": True})
    assert available_response.status_code == 200
    return available_response.json()


@pytest.mark.asyncio
async def test_returns_empty_list_when_nothing_is_active(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_a_pending_item_appears_with_its_correct_table_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    order, table = await _open_table(client, db_session, table_number=1)
    dish = await _create_available_dish(client, db_session, "Margherita")
    await _login(client, "waiter-1")
    item = await _add_item(client, order["id"], dish["id"], quantity=2)
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == item["id"]
    assert body[0]["order_id"] == order["id"]
    assert body[0]["table_id"] == table["id"]
    assert body[0]["dish_id"] == dish["id"]
    assert body[0]["quantity"] == 2
    assert body[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_items_across_two_tables_each_carry_their_own_table_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    order1, table1 = await _open_table(client, db_session, table_number=1)
    order2, table2 = await _open_table(client, db_session, table_number=2)
    dish = await _create_available_dish(client, db_session, "Tiramisu")
    await _login(client, "waiter-1")
    item1 = await _add_item(client, order1["id"], dish["id"])
    await _login(client, "waiter-2")
    item2 = await _add_item(client, order2["id"], dish["id"])
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert: proves the join resolves the real table_id per row, not a
    # hardcoded or first-row value.
    body = response.json()
    by_item_id = {row["id"]: row for row in body}
    assert by_item_id[item1["id"]]["table_id"] == table1["id"]
    assert by_item_id[item2["id"]]["table_id"] == table2["id"]


@pytest.mark.asyncio
async def test_a_cancelled_item_is_excluded(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    order, _table = await _open_table(client, db_session, table_number=1)
    dish = await _create_available_dish(client, db_session, "Fries")
    await _login(client, "waiter-1")
    item = await _add_item(client, order["id"], dish["id"])
    cancel_response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")
    assert cancel_response.status_code == 200
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    assert response.json() == []


@pytest.mark.asyncio
async def test_in_preparation_and_ready_items_are_included(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: no API path exists yet to reach in_preparation/ready (Story
    # 5.2), so these are inserted directly, matching this codebase's existing
    # shortcut for fixture setup with no API path yet.
    order, _table = await _open_table(client, db_session, table_number=1)
    dish = await _create_available_dish(client, db_session, "Espresso")
    await _login(client, "waiter-1")
    pending_item = await _add_item(client, order["id"], dish["id"])
    in_prep_item = await _add_item(client, order["id"], dish["id"])
    ready_item = await _add_item(client, order["id"], dish["id"])

    in_prep_row = await db_session.get(OrderItem, in_prep_item["id"])
    in_prep_row.status = OrderItemStatus.in_preparation
    ready_row = await db_session.get(OrderItem, ready_item["id"])
    ready_row.status = OrderItemStatus.ready
    await db_session.commit()

    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    ids = {row["id"] for row in response.json()}
    assert ids == {pending_item["id"], in_prep_item["id"], ready_item["id"]}


@pytest.mark.asyncio
async def test_a_served_orders_ready_item_is_excluded(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: a ready item whose Order is then marked served via the real serve flow (Story
    # 5.4), not a direct DB write — this is the gap Story 5.3's own docstring flagged: a served
    # Order's items keep their own ready status and would otherwise leak onto this board forever.
    order, _table = await _open_table(client, db_session, table_number=1)
    dish = await _create_available_dish(client, db_session, "Served Leak Dish")
    await _login(client, "waiter-1")
    item = await _add_item(client, order["id"], dish["id"])
    ready_row = await db_session.get(OrderItem, item["id"])
    ready_row.status = OrderItemStatus.ready
    order_row = await db_session.get(Order, order["id"])
    order_row.status = OrderStatus.ready
    await db_session.commit()

    serve_response = await client.post(f"/api/orders/{order['id']}/serve")
    assert serve_response.status_code == 200

    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    assert response.json() == []


@pytest.mark.asyncio
async def test_a_rejected_item_is_excluded(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    order, _table = await _open_table(client, db_session, table_number=1)
    dish = await _create_available_dish(client, db_session, "Rejected Fries")
    await _login(client, "waiter-1")
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as(client, db_session, UserRole.cook, "amir")
    reject_response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/reject")
    assert reject_response.status_code == 200

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert: excluded from the board the same way a cancelled item always has been.
    assert response.json() == []


@pytest.mark.asyncio
async def test_a_pending_item_with_enough_stock_reports_its_full_quantity_as_preparable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: 10.000 in stock, 1.000 per portion -> 10 preparable, well above the 2 ordered.
    order, _table = await _open_table(client, db_session, table_number=1)
    dish = await _create_available_dish_with_stock(
        client, db_session, "Plenty Stock Dish", ingredient_stock="10.000", recipe_quantity="1.000"
    )
    await _login(client, "waiter-1")
    item = await _add_item(client, order["id"], dish["id"], quantity=2)
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    body = response.json()
    assert len(body) == 1
    assert body[0]["max_preparable_quantity"] == 10


@pytest.mark.asyncio
async def test_a_pending_item_with_insufficient_stock_reports_its_true_max_preparable_quantity(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: 3.000 in stock, 1.000 per portion -> only 3 preparable, but 10 were ordered.
    order, _table = await _open_table(client, db_session, table_number=1)
    dish = await _create_available_dish_with_stock(
        client, db_session, "Short Stock Dish", ingredient_stock="3.000", recipe_quantity="1.000"
    )
    await _login(client, "waiter-1")
    item = await _add_item(client, order["id"], dish["id"], quantity=10)
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    body = response.json()
    assert len(body) == 1
    assert body[0]["max_preparable_quantity"] == 3
    assert body[0]["quantity"] == 10


@pytest.mark.asyncio
async def test_an_in_preparation_items_max_preparable_quantity_is_its_own_quantity(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: already picked up (stock already reserved for it) — its own field must not flag a
    # false shortage now that current stock reflects its own deduction.
    order, _table = await _open_table(client, db_session, table_number=1)
    dish = await _create_available_dish(client, db_session, "In Prep Stock Dish")
    await _login(client, "waiter-1")
    item = await _add_item(client, order["id"], dish["id"], quantity=3)
    await _login_as(client, db_session, UserRole.cook, "amir")
    pick_up_response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    assert pick_up_response.status_code == 200

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    body = response.json()
    assert len(body) == 1
    assert body[0]["max_preparable_quantity"] == 3
    assert body[0]["status"] == "in_preparation"


@pytest.mark.asyncio
async def test_admin_can_also_read_kitchen_items(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.admin, "admin1")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_waiter_cannot_read_kitchen_items(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.waiter, "maya")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_warehouse_manager_cannot_read_kitchen_items(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")

    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_read_kitchen_items(client: AsyncClient) -> None:
    # Act
    response = await client.get("/api/kitchen/items")

    # Assert
    assert response.status_code == 401
