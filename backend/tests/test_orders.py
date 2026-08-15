import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import Ingredient, Order, RestaurantTable, TableStatus, Unit, User, UserRole
from services.auth_service import AuthService
from services.order_service import OrderService

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


async def _login_as_admin(client: AsyncClient, db_session: AsyncSession, username: str = "admin1") -> User:
    admin = await _create_user(db_session, username=username, role=UserRole.admin)
    await _login(client, username)
    return admin


async def _login_as_waiter(client: AsyncClient, db_session: AsyncSession, username: str = "waiter1") -> User:
    waiter = await _create_user(db_session, username=username, role=UserRole.waiter)
    await _login(client, username)
    return waiter


async def _create_table(client: AsyncClient, db_session: AsyncSession, table_number: int = 1) -> dict:
    admin = await _create_user(db_session, "table-admin", UserRole.admin)
    await _login(client, "table-admin")
    response = await client.post("/api/tables", json={"table_number": table_number, "capacity": 4})
    assert response.status_code == 201
    return response.json()


async def _open_table(
    client: AsyncClient, db_session: AsyncSession, table_number: int = 1
) -> tuple[dict, User, dict]:
    table = await _create_table(client, db_session, table_number)
    waiter = await _login_as_waiter(client, db_session, username=f"waiter-{table_number}")
    response = await client.post(f"/api/orders/tables/{table['id']}/open")
    assert response.status_code == 201
    return response.json(), waiter, table


async def _create_dish(client: AsyncClient, name: str = "Margherita", price: str = "12.50") -> dict:
    category_response = await client.post("/api/menu/categories", json={"name": f"{name} Category"})
    assert category_response.status_code == 201
    category = category_response.json()
    dish_response = await client.post(
        "/api/menu/dishes",
        json={"name": name, "price": price, "category_id": category["id"], "prep_time_minutes": 15},
    )
    assert dish_response.status_code == 201
    return dish_response.json()


async def _create_available_dish(
    client: AsyncClient, db_session: AsyncSession, name: str = "Margherita", price: str = "12.50"
) -> dict:
    await _create_user(db_session, f"dish-admin-{name}", UserRole.admin)
    await _login(client, f"dish-admin-{name}")
    dish = await _create_dish(client, name, price)
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


@pytest.mark.asyncio
async def test_waiter_can_open_an_available_table(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    table = await _create_table(client, db_session)
    waiter = await _login_as_waiter(client, db_session)

    # Act
    response = await client.post(f"/api/orders/tables/{table['id']}/open")

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["waiter_id"] == waiter.id
    assert body["table_id"] == table["id"]

    # Assert: the table's status really changed, not just the response body.
    db_session.expire_all()
    db_table = await db_session.get(RestaurantTable, table["id"])
    assert db_table.status is TableStatus.occupied


@pytest.mark.asyncio
async def test_opening_an_already_occupied_table_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    table = await _create_table(client, db_session)
    db_table = await db_session.get(RestaurantTable, table["id"])
    db_table.status = TableStatus.occupied
    await db_session.commit()
    await _login_as_waiter(client, db_session)

    # Act
    response = await client.post(f"/api/orders/tables/{table['id']}/open")

    # Assert
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_opening_a_reserved_table_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: AC2 treats reserved identically to occupied.
    table = await _create_table(client, db_session)
    db_table = await db_session.get(RestaurantTable, table["id"])
    db_table.status = TableStatus.reserved
    await db_session.commit()
    await _login_as_waiter(client, db_session)

    # Act
    response = await client.post(f"/api/orders/tables/{table['id']}/open")

    # Assert
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_opening_a_nonexistent_table_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_waiter(client, db_session)

    # Act
    response = await client.post("/api/orders/tables/999999/open")

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_cannot_open_a_table(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    table = await _create_table(client, db_session)
    await _login_as_admin(client, db_session)

    # Act
    response = await client.post(f"/api/orders/tables/{table['id']}/open")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cook_cannot_open_a_table(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    table = await _create_table(client, db_session)
    await _create_user(db_session, "cook1", UserRole.cook)
    await _login(client, "cook1")

    # Act
    response = await client.post(f"/api/orders/tables/{table['id']}/open")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_warehouse_manager_cannot_open_a_table(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    table = await _create_table(client, db_session)
    await _create_user(db_session, "wh1", UserRole.warehouse_manager)
    await _login(client, "wh1")

    # Act
    response = await client.post(f"/api/orders/tables/{table['id']}/open")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_open_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: _create_table logs in as an Admin to create the table, so that
    # session cookie must be cleared to test a truly unauthenticated request.
    table = await _create_table(client, db_session)
    client.cookies.clear()

    # Act
    response = await client.post(f"/api/orders/tables/{table['id']}/open")

    # Assert
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_race_between_two_opens_only_one_succeeds(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: the table is available when this request's read step runs, but a
    # second open lands from a separate session strictly between that read and
    # this request's guarded UPDATE. A naive read-then-write would let this
    # through; only the WHERE status = 'available' guard on the UPDATE itself
    # catches it.
    table = await _create_table(client, db_session)
    table_id = table["id"]
    await _login_as_waiter(client, db_session)

    original_get_table = OrderService._get_table

    async def get_table_then_seat_it(self, db, actor, requested_id):
        loaded = await original_get_table(self, db, actor, requested_id)
        assert loaded.status is TableStatus.available
        seated = await db_session.get(RestaurantTable, requested_id)
        seated.status = TableStatus.occupied
        db_session.add(Order(table_id=requested_id, waiter_id=actor.id))
        await db_session.commit()
        return loaded

    monkeypatch.setattr(OrderService, "_get_table", get_table_then_seat_it)

    # Act
    response = await client.post(f"/api/orders/tables/{table_id}/open")

    # Assert
    assert response.status_code == 409

    # Assert: only the racing session's Order exists, none from this request.
    monkeypatch.undo()
    db_session.expire_all()
    db_table = await db_session.get(RestaurantTable, table_id)
    assert db_table.status is TableStatus.occupied


@pytest.mark.asyncio
async def test_waiter_can_list_tables(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    table = await _create_table(client, db_session)
    await _login_as_waiter(client, db_session)

    # Act
    response = await client.get("/api/tables")

    # Assert
    assert response.status_code == 200
    assert any(t["id"] == table["id"] for t in response.json())


@pytest.mark.asyncio
async def test_cook_cannot_list_tables(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _create_user(db_session, "cook2", UserRole.cook)
    await _login(client, "cook2")

    # Act
    response = await client.get("/api/tables")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_warehouse_manager_cannot_list_tables(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _create_user(db_session, "wh2", UserRole.warehouse_manager)
    await _login(client, "wh2")

    # Act
    response = await client.get("/api/tables")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_waiter_can_fetch_the_open_order_for_a_table(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    order, _waiter, table = await _open_table(client, db_session)

    # Act
    response = await client.get(f"/api/orders/tables/{table['id']}")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == order["id"]
    assert body["table_id"] == table["id"]


@pytest.mark.asyncio
async def test_fetching_order_for_a_table_with_no_open_order_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: the table exists but was never opened, so it has no Order at all.
    table = await _create_table(client, db_session)
    await _login_as_waiter(client, db_session)

    # Act
    response = await client.get(f"/api/orders/tables/{table['id']}")

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_fetching_order_for_a_nonexistent_table_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_waiter(client, db_session)

    # Act
    response = await client.get("/api/orders/tables/999999")

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_waiter_can_add_an_available_dish_to_an_open_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Shakshuka")
    order, _waiter, _table = await _open_table(client, db_session, table_number=2)

    # Act
    response = await client.post(
        f"/api/orders/{order['id']}/items",
        json={"dish_id": dish["id"], "quantity": 2, "notes": "no onions"},
    )

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["order_id"] == order["id"]
    assert body["dish_id"] == dish["id"]
    assert body["status"] == "pending"
    assert body["quantity"] == 2
    assert body["notes"] == "no onions"
    assert body["price_at_add"] == dish["price"]


@pytest.mark.asyncio
async def test_adding_an_unavailable_dish_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _create_user(db_session, "dish-admin-unavailable", UserRole.admin)
    await _login(client, "dish-admin-unavailable")
    dish = await _create_dish(client, "Unavailable Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=3)

    # Act
    response = await client.post(
        f"/api/orders/{order['id']}/items", json={"dish_id": dish["id"], "quantity": 1}
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, dish unavailable"


@pytest.mark.asyncio
async def test_adding_a_nonexistent_dish_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    order, _waiter, _table = await _open_table(client, db_session, table_number=4)

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items", json={"dish_id": 999999, "quantity": 1})

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_adding_an_item_to_a_nonexistent_order_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Ghost Order Dish")
    await _login_as_waiter(client, db_session, username="waiter-ghost")

    # Act
    response = await client.post("/api/orders/999999/items", json={"dish_id": dish["id"], "quantity": 1})

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_order_items_list_starts_empty_and_reflects_additions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="List Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=5)

    # Act: a fresh Order has no items yet.
    empty_response = await client.get(f"/api/orders/{order['id']}/items")

    # Assert
    assert empty_response.status_code == 200
    assert empty_response.json() == []

    # Act: add two items.
    first = await client.post(f"/api/orders/{order['id']}/items", json={"dish_id": dish["id"], "quantity": 1})
    assert first.status_code == 201
    second = await client.post(
        f"/api/orders/{order['id']}/items",
        json={"dish_id": dish["id"], "quantity": 3, "notes": "extra spicy"},
    )
    assert second.status_code == 201
    list_response = await client.get(f"/api/orders/{order['id']}/items")

    # Assert
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 2
    assert items[0]["id"] == first.json()["id"]
    assert items[1]["id"] == second.json()["id"]
    assert items[1]["notes"] == "extra spicy"
    assert items[1]["quantity"] == 3


@pytest.mark.asyncio
async def test_admin_cannot_use_order_item_endpoints(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Admin Blocked Dish")
    order, _waiter, table = await _open_table(client, db_session, table_number=6)
    await _create_user(db_session, "blocked-admin", UserRole.admin)
    await _login(client, "blocked-admin")

    # Act / Assert
    assert (await client.get(f"/api/orders/tables/{table['id']}")).status_code == 403
    assert (await client.get(f"/api/orders/{order['id']}/items")).status_code == 403
    assert (
        await client.post(f"/api/orders/{order['id']}/items", json={"dish_id": dish["id"], "quantity": 1})
    ).status_code == 403


@pytest.mark.asyncio
async def test_cook_cannot_use_order_item_endpoints(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Cook Blocked Dish")
    order, _waiter, table = await _open_table(client, db_session, table_number=7)
    await _create_user(db_session, "blocked-cook", UserRole.cook)
    await _login(client, "blocked-cook")

    # Act / Assert
    assert (await client.get(f"/api/orders/tables/{table['id']}")).status_code == 403
    assert (await client.get(f"/api/orders/{order['id']}/items")).status_code == 403
    assert (
        await client.post(f"/api/orders/{order['id']}/items", json={"dish_id": dish["id"], "quantity": 1})
    ).status_code == 403


@pytest.mark.asyncio
async def test_warehouse_manager_cannot_use_order_item_endpoints(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Warehouse Blocked Dish")
    order, _waiter, table = await _open_table(client, db_session, table_number=8)
    await _create_user(db_session, "blocked-wh", UserRole.warehouse_manager)
    await _login(client, "blocked-wh")

    # Act / Assert
    assert (await client.get(f"/api/orders/tables/{table['id']}")).status_code == 403
    assert (await client.get(f"/api/orders/{order['id']}/items")).status_code == 403
    assert (
        await client.post(f"/api/orders/{order['id']}/items", json={"dish_id": dish["id"], "quantity": 1})
    ).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_use_order_item_endpoints(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Anon Blocked Dish")
    order, _waiter, table = await _open_table(client, db_session, table_number=9)
    client.cookies.clear()

    # Act / Assert
    assert (await client.get(f"/api/orders/tables/{table['id']}")).status_code == 401
    assert (await client.get(f"/api/orders/{order['id']}/items")).status_code == 401
    assert (
        await client.post(f"/api/orders/{order['id']}/items", json={"dish_id": dish["id"], "quantity": 1})
    ).status_code == 401


@pytest.mark.asyncio
async def test_price_at_add_is_unaffected_by_a_later_dish_price_change(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: AD-7, add an item, then change the Dish's price.
    dish = await _create_available_dish(client, db_session, name="Price Lock Dish", price="20.00")
    order, waiter, _table = await _open_table(client, db_session, table_number=10)
    add_response = await client.post(
        f"/api/orders/{order['id']}/items", json={"dish_id": dish["id"], "quantity": 1}
    )
    assert add_response.status_code == 201
    item_id = add_response.json()["id"]
    assert add_response.json()["price_at_add"] == "20.00"

    await _create_user(db_session, "price-admin", UserRole.admin)
    await _login(client, "price-admin")
    patch_response = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"price": "35.00"})
    assert patch_response.status_code == 200

    # Act: re-fetch the item as the Waiter, after the price change.
    await _login(client, waiter.username)
    items_response = await client.get(f"/api/orders/{order['id']}/items")

    # Assert
    assert items_response.status_code == 200
    item = next(i for i in items_response.json() if i["id"] == item_id)
    assert item["price_at_add"] == "20.00"
