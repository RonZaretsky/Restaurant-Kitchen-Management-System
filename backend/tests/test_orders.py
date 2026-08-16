from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import (
    Ingredient,
    Order,
    OrderItem,
    OrderItemStatus,
    RecipeIngredient,
    RestaurantTable,
    StockMovement,
    TableStatus,
    Unit,
    User,
    UserRole,
)
from data_models.order import MAX_ORDER_ITEM_QUANTITY
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


async def _login_as_cook(client: AsyncClient, db_session: AsyncSession, username: str = "cook1") -> User:
    cook = await _create_user(db_session, username=username, role=UserRole.cook)
    await _login(client, username)
    return cook


async def _create_table(client: AsyncClient, db_session: AsyncSession, table_number: int = 1) -> dict:
    # Username derived from table_number, not a fixed literal: table_number is
    # already required to be unique across every call site in this file, so
    # this stays a no-op rename for every existing single-call test while
    # letting a test that opens two tables of its own (Story 3.4's
    # different-order tests) do so without a duplicate-username collision.
    admin_username = f"table-admin-{table_number}"
    await _create_user(db_session, admin_username, UserRole.admin)
    await _login(client, admin_username)
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


async def _create_available_dish_with_ingredient(
    client: AsyncClient,
    db_session: AsyncSession,
    name: str = "Margherita",
    price: str = "12.50",
    ingredient_stock: str = "10.000",
    ingredient_threshold: str = "1.000",
    recipe_quantity: str = "0.500",
) -> tuple[dict, int]:
    # Same shape as _create_available_dish, but returns the backing Ingredient's
    # plain id (not the ORM object) too, so pick-up tests can assert
    # current_stock and control the starting stock/threshold precisely.
    # Returning the plain id, not the ORM instance, avoids a MissingGreenlet
    # crash: accessing an attribute on an ORM object after db_session.expire_all()
    # triggers a synchronous lazy-load, which an AsyncSession cannot perform
    # outside an explicit await — every caller must already have the id as a
    # plain int before expiring the session, matching every other fixture
    # helper in this file's own "pass ids, not ORM objects" convention.
    await _create_user(db_session, f"pickup-dish-admin-{name}", UserRole.admin)
    await _login(client, f"pickup-dish-admin-{name}")
    dish = await _create_dish(client, name, price)
    ingredient = Ingredient(
        name=f"{name} Ingredient", unit=Unit.kg, current_stock=ingredient_stock, min_stock_threshold=ingredient_threshold
    )
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    ingredient_id = ingredient.id
    recipe_response = await client.post(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients",
        json={"ingredient_id": ingredient_id, "quantity": recipe_quantity, "unit": "kg"},
    )
    assert recipe_response.status_code == 201
    available_response = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"is_available": True})
    assert available_response.status_code == 200
    return available_response.json(), ingredient_id


async def _add_item(
    client: AsyncClient, order_id: int, dish_id: int, quantity: int = 1, notes: str | None = None
) -> dict:
    payload: dict = {"dish_id": dish_id, "quantity": quantity}
    if notes is not None:
        payload["notes"] = notes
    response = await client.post(f"/api/orders/{order_id}/items", json=payload)
    assert response.status_code == 201
    return response.json()


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
async def test_cook_can_list_tables(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: Story 5.1 widened TablesReadDep so the Kitchen Display can
    # resolve table_number client-side, mirroring the Waiter's own precedent.
    await _create_user(db_session, "cook2", UserRole.cook)
    await _login(client, "cook2")

    # Act
    response = await client.get("/api/tables")

    # Assert
    assert response.status_code == 200


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

    # Assert: the row really carries the dish's price, not just the response body.
    db_session.expire_all()
    db_item = await db_session.get(OrderItem, body["id"])
    assert db_item.price_at_add == Decimal(dish["price"])
    assert db_item.status is OrderItemStatus.pending
    assert db_item.quantity == 2
    assert db_item.notes == "no onions"


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


@pytest.mark.asyncio
async def test_waiter_can_list_dishes(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: the Table/Order detail screen cannot render its dish picker without
    # this read, so Story 3.2 widened GET /api/menu/dishes to permit a Waiter.
    dish = await _create_available_dish(client, db_session, name="Waiter Readable Dish")
    await _login_as_waiter(client, db_session, username="waiter-menu")

    # Act
    response = await client.get("/api/menu/dishes")

    # Assert
    assert response.status_code == 200
    assert any(d["id"] == dish["id"] for d in response.json())


@pytest.mark.asyncio
async def test_warehouse_manager_cannot_list_dishes(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: the widening above is Waiter-only, no AC grants a Warehouse Manager
    # the dish catalog.
    await _create_user(db_session, "wh-menu", UserRole.warehouse_manager)
    await _login(client, "wh-menu")

    # Act
    response = await client.get("/api/menu/dishes")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_waiter_cannot_read_a_dishs_recipe(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: the dish-list widening is deliberately narrower than MenuReadDep,
    # a Waiter gets the catalog but never the kitchen-side recipe.
    dish = await _create_available_dish(client, db_session, name="Recipe Guarded Dish")
    await _login_as_waiter(client, db_session, username="waiter-recipe")

    # Act
    response = await client.get(f"/api/menu/dishes/{dish['id']}/recipe-ingredients")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_quantity_above_the_cap_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: quantity is capped so price_at_add * quantity stays inside
    # Order.total_amount's Numeric(10, 2) range (FR-8/AD-7).
    dish = await _create_available_dish(client, db_session, name="Capped Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=11)

    # Act
    response = await client.post(
        f"/api/orders/{order['id']}/items",
        json={"dish_id": dish["id"], "quantity": MAX_ORDER_ITEM_QUANTITY + 1},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_quantity_at_the_cap_is_accepted(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: the cap itself is a valid value, the boundary is inclusive.
    dish = await _create_available_dish(client, db_session, name="At Cap Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=12)

    # Act
    response = await client.post(
        f"/api/orders/{order['id']}/items",
        json={"dish_id": dish["id"], "quantity": MAX_ORDER_ITEM_QUANTITY},
    )

    # Assert
    assert response.status_code == 201
    assert response.json()["quantity"] == MAX_ORDER_ITEM_QUANTITY


@pytest.mark.asyncio
async def test_waiter_can_edit_a_pending_items_quantity_and_note(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Edit Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=20)
    item = await _add_item(client, order["id"], dish["id"], quantity=1)

    # Act
    response = await client.patch(
        f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 4, "notes": "extra spicy"}
    )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["quantity"] == 4
    assert body["notes"] == "extra spicy"
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_waiter_can_cancel_a_pending_item(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Waiter Cancel Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=21)
    item = await _add_item(client, order["id"], dish["id"])

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cook_can_cancel_a_pending_item(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Cook Cancel Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=22)
    item = await _add_item(client, order["id"], dish["id"])
    await _create_user(db_session, "cancel-cook", UserRole.cook)
    await _login(client, "cancel-cook")

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_admin_can_cancel_a_pending_item(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Admin Cancel Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=23)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_admin(client, db_session, "cancel-admin")

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancelling_an_in_preparation_item_succeeds_without_reversing_stock(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: no automatic-deduction code exists yet (Epic 5), so in_preparation
    # is reached by setting the row directly, matching this file's own
    # precedent of pre-setting blocking state via db_session when no real
    # transition endpoint exists to reach it through.
    dish = await _create_available_dish(client, db_session, name="In Prep Cancel Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=24)
    item = await _add_item(client, order["id"], dish["id"])
    db_item = await db_session.get(OrderItem, item["id"])
    db_item.status = OrderItemStatus.in_preparation
    await db_session.commit()

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")

    # Assert: cancelled, and no stock-related code path exists to have run or
    # failed, AD-11 is a prohibition, not a feature, there is nothing to assert
    # was reversed because nothing auto-deducts yet.
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_editing_an_in_preparation_item_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="In Prep Edit Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=25)
    item = await _add_item(client, order["id"], dish["id"])
    db_item = await db_session.get(OrderItem, item["id"])
    db_item.status = OrderItemStatus.in_preparation
    await db_session.commit()

    # Act
    response = await client.patch(
        f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 9}
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, item not pending"


@pytest.mark.asyncio
async def test_editing_a_ready_item_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Ready Edit Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=26)
    item = await _add_item(client, order["id"], dish["id"])
    db_item = await db_session.get(OrderItem, item["id"])
    db_item.status = OrderItemStatus.ready
    await db_session.commit()

    # Act
    response = await client.patch(
        f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 2}
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, item not pending"


@pytest.mark.asyncio
async def test_cancelling_a_ready_item_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Ready Cancel Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=27)
    item = await _add_item(client, order["id"], dish["id"])
    db_item = await db_session.get(OrderItem, item["id"])
    db_item.status = OrderItemStatus.ready
    await db_session.commit()

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, item not cancellable"


@pytest.mark.asyncio
async def test_editing_an_already_cancelled_item_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Cancelled Edit Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=28)
    item = await _add_item(client, order["id"], dish["id"])
    cancel_response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")
    assert cancel_response.status_code == 200

    # Act
    response = await client.patch(
        f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 3}
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, item not pending"


@pytest.mark.asyncio
async def test_cancelling_an_already_cancelled_item_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Double Cancel Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=29)
    item = await _add_item(client, order["id"], dish["id"])
    first_cancel = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")
    assert first_cancel.status_code == 200

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, item not cancellable"


@pytest.mark.asyncio
async def test_editing_a_nonexistent_item_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    order, _waiter, _table = await _open_table(client, db_session, table_number=30)

    # Act
    response = await client.patch(
        f"/api/orders/{order['id']}/items/999999", json={"quantity": 2}
    )

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancelling_a_nonexistent_item_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    order, _waiter, _table = await _open_table(client, db_session, table_number=31)

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/999999/cancel")

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_editing_an_item_belonging_to_a_different_order_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Cross Order Edit Dish")
    order_a, _waiter_a, _table_a = await _open_table(client, db_session, table_number=32)
    item = await _add_item(client, order_a["id"], dish["id"])
    order_b, _waiter_b, _table_b = await _open_table(client, db_session, table_number=33)

    # Act: item belongs to order_a, addressed here via order_b's id.
    response = await client.patch(
        f"/api/orders/{order_b['id']}/items/{item['id']}", json={"quantity": 2}
    )

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancelling_an_item_belonging_to_a_different_order_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Cross Order Cancel Dish")
    order_a, _waiter_a, _table_a = await _open_table(client, db_session, table_number=34)
    item = await _add_item(client, order_a["id"], dish["id"])
    order_b, _waiter_b, _table_b = await _open_table(client, db_session, table_number=35)

    # Act
    response = await client.post(f"/api/orders/{order_b['id']}/items/{item['id']}/cancel")

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_warehouse_manager_cannot_edit_or_cancel_an_item(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="WH Blocked Item Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=36)
    item = await _add_item(client, order["id"], dish["id"])
    await _create_user(db_session, "item-blocked-wh", UserRole.warehouse_manager)
    await _login(client, "item-blocked-wh")

    # Act / Assert
    assert (
        await client.patch(f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 2})
    ).status_code == 403
    assert (
        await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")
    ).status_code == 403


@pytest.mark.asyncio
async def test_cook_cannot_edit_an_item(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: edit stays Waiter-only, unlike cancel.
    dish = await _create_available_dish(client, db_session, name="Cook Blocked Edit Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=37)
    item = await _add_item(client, order["id"], dish["id"])
    await _create_user(db_session, "edit-blocked-cook", UserRole.cook)
    await _login(client, "edit-blocked-cook")

    # Act
    response = await client.patch(
        f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 2}
    )

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_edit_an_item(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Admin Blocked Edit Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=38)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_admin(client, db_session, "edit-blocked-admin")

    # Act
    response = await client.patch(
        f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 2}
    )

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_edit_or_cancel_an_item(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Anon Blocked Item Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=39)
    item = await _add_item(client, order["id"], dish["id"])
    client.cookies.clear()

    # Act / Assert
    assert (
        await client.patch(f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 2})
    ).status_code == 401
    assert (
        await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")
    ).status_code == 401


@pytest.mark.asyncio
async def test_race_between_edit_and_a_competing_transition_only_one_succeeds(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: the item is pending when this request's read step runs, but a
    # second request moves it to in_preparation strictly between that read and
    # this request's guarded UPDATE.
    dish = await _create_available_dish(client, db_session, name="Race Edit Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=40)
    item = await _add_item(client, order["id"], dish["id"])

    original_get_item = OrderService._get_item

    async def get_item_then_start_prep(self, db, actor, requested_order_id, requested_item_id):
        loaded = await original_get_item(self, db, actor, requested_order_id, requested_item_id)
        assert loaded.status is OrderItemStatus.pending
        racing = await db_session.get(OrderItem, requested_item_id)
        racing.status = OrderItemStatus.in_preparation
        await db_session.commit()
        return loaded

    monkeypatch.setattr(OrderService, "_get_item", get_item_then_start_prep)

    # Act
    response = await client.patch(
        f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 5}
    )

    # Assert
    assert response.status_code == 409

    # Assert: the write did not land.
    monkeypatch.undo()
    db_session.expire_all()
    unchanged = await db_session.get(OrderItem, item["id"])
    assert unchanged.quantity == 1
    assert unchanged.status is OrderItemStatus.in_preparation


@pytest.mark.asyncio
async def test_race_between_cancel_and_a_competing_transition_only_one_succeeds(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: the item is pending when this request's read step runs, but a
    # second request moves it to ready strictly between that read and this
    # request's guarded UPDATE.
    dish = await _create_available_dish(client, db_session, name="Race Cancel Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=41)
    item = await _add_item(client, order["id"], dish["id"])

    original_get_item = OrderService._get_item

    async def get_item_then_mark_ready(self, db, actor, requested_order_id, requested_item_id):
        loaded = await original_get_item(self, db, actor, requested_order_id, requested_item_id)
        assert loaded.status is OrderItemStatus.pending
        racing = await db_session.get(OrderItem, requested_item_id)
        racing.status = OrderItemStatus.ready
        await db_session.commit()
        return loaded

    monkeypatch.setattr(OrderService, "_get_item", get_item_then_mark_ready)

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")

    # Assert
    assert response.status_code == 409

    # Assert: the write did not land.
    monkeypatch.undo()
    db_session.expire_all()
    unchanged = await db_session.get(OrderItem, item["id"])
    assert unchanged.status is OrderItemStatus.ready


@pytest.mark.asyncio
async def test_last_write_wins_on_two_sequential_edits(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="LWW Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=42)
    item = await _add_item(client, order["id"], dish["id"])

    # Act: two sequential edits, simulating two overlapping actors, both succeed.
    first = await client.patch(f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 2})
    second = await client.patch(f"/api/orders/{order['id']}/items/{item['id']}", json={"quantity": 5})

    # Assert: no conflict response, the second commit simply wins (NFR-6).
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["quantity"] == 5


# --- Story 5.2: pick-up and mark-ready -------------------------------------------------------


@pytest.mark.asyncio
async def test_picking_up_a_pending_item_deducts_stock_and_records_the_cook(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish, ingredient = await _create_available_dish_with_ingredient(client, db_session, name="Pickup Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=50)
    item = await _add_item(client, order["id"], dish["id"])
    cook = await _login_as_cook(client, db_session, "pickup-cook-1")
    cook_id = cook.id

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_preparation"
    assert body["cook_id"] == cook_id

    db_session.expire_all()
    updated_ingredient = await db_session.get(Ingredient, ingredient)
    assert updated_ingredient.current_stock == Decimal("9.500")

    movements = await db_session.execute(select(StockMovement).where(StockMovement.ingredient_id == ingredient))
    movement_rows = movements.scalars().all()
    assert len(movement_rows) == 1
    assert movement_rows[0].movement_type.value == "consumption"
    assert movement_rows[0].quantity_change == Decimal("-0.500")
    assert movement_rows[0].reference_id == order["id"]
    assert movement_rows[0].performed_by == cook_id


@pytest.mark.asyncio
async def test_picking_up_deducts_every_recipe_ingredient(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: a Dish with two Recipe Ingredients.
    await _create_user(db_session, "multi-dish-admin", UserRole.admin)
    await _login(client, "multi-dish-admin")
    dish = await _create_dish(client, "Multi-Ingredient Dish", "18.00")
    flour = Ingredient(name="Flour", unit=Unit.kg, current_stock="10.000", min_stock_threshold="1.000")
    cheese = Ingredient(name="Cheese", unit=Unit.kg, current_stock="5.000", min_stock_threshold="0.500")
    db_session.add_all([flour, cheese])
    await db_session.commit()
    await db_session.refresh(flour)
    await db_session.refresh(cheese)
    flour_id = flour.id
    cheese_id = cheese.id
    for ingredient_id, quantity in ((flour_id, "0.300"), (cheese_id, "0.200")):
        recipe_response = await client.post(
            f"/api/menu/dishes/{dish['id']}/recipe-ingredients",
            json={"ingredient_id": ingredient_id, "quantity": quantity, "unit": "kg"},
        )
        assert recipe_response.status_code == 201
    available_response = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"is_available": True})
    assert available_response.status_code == 200
    dish = available_response.json()

    order, _waiter, _table = await _open_table(client, db_session, table_number=51)
    item = await _add_item(client, order["id"], dish["id"], quantity=2)
    await _login_as_cook(client, db_session, "multi-cook")

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")

    # Assert: quantity=2, so each ingredient is deducted by (recipe quantity * 2).
    assert response.status_code == 200
    db_session.expire_all()
    updated_flour = await db_session.get(Ingredient, flour_id)
    updated_cheese = await db_session.get(Ingredient, cheese_id)
    assert updated_flour.current_stock == Decimal("9.400")
    assert updated_cheese.current_stock == Decimal("4.600")

    flour_movements = await db_session.execute(select(StockMovement).where(StockMovement.ingredient_id == flour_id))
    cheese_movements = await db_session.execute(select(StockMovement).where(StockMovement.ingredient_id == cheese_id))
    assert len(flour_movements.scalars().all()) == 1
    assert len(cheese_movements.scalars().all()) == 1


@pytest.mark.asyncio
async def test_picking_up_the_same_item_twice_does_not_double_deduct(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish, ingredient = await _create_available_dish_with_ingredient(client, db_session, name="No Double Deduct Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=52)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "no-double-cook")

    # Act
    first = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    second = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")

    # Assert
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == "Rejected, item not pending"

    db_session.expire_all()
    updated_ingredient = await db_session.get(Ingredient, ingredient)
    assert updated_ingredient.current_stock == Decimal("9.500")
    movements = await db_session.execute(select(StockMovement).where(StockMovement.ingredient_id == ingredient))
    assert len(movements.scalars().all()) == 1


@pytest.mark.asyncio
async def test_marking_an_in_preparation_item_ready_is_a_pure_status_change(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish, ingredient = await _create_available_dish_with_ingredient(client, db_session, name="Ready Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=53)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "ready-cook")
    pick_up = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    assert pick_up.status_code == 200

    db_session.expire_all()
    stock_after_pickup = (await db_session.get(Ingredient, ingredient)).current_stock

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "ready"

    db_session.expire_all()
    assert (await db_session.get(Ingredient, ingredient)).current_stock == stock_after_pickup
    movements = await db_session.execute(select(StockMovement).where(StockMovement.ingredient_id == ingredient))
    assert len(movements.scalars().all()) == 1


@pytest.mark.asyncio
async def test_pending_item_cannot_skip_directly_to_ready(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Skip Ahead Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=54)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "skip-cook")

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, item not in preparation"
    db_session.expire_all()
    unchanged = await db_session.get(OrderItem, item["id"])
    assert unchanged.status is OrderItemStatus.pending


@pytest.mark.asyncio
async def test_in_preparation_item_pick_up_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Already In Prep Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=55)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "already-prep-cook")
    pick_up = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    assert pick_up.status_code == 200

    # Act: pick-up again on the now in_preparation item.
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, item not pending"


@pytest.mark.asyncio
async def test_ready_item_pick_up_and_mark_ready_are_both_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Already Ready Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=56)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "already-ready-cook")
    pick_up = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    assert pick_up.status_code == 200
    mark_ready = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")
    assert mark_ready.status_code == 200

    # Act
    pick_up_again = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    mark_ready_again = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")

    # Assert: no undo, both reverse/re-transition attempts are rejected.
    assert pick_up_again.status_code == 409
    assert mark_ready_again.status_code == 409


@pytest.mark.asyncio
async def test_a_different_active_cook_can_mark_ready_an_item_picked_up_by_a_deactivated_cook(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: Cook A picks up the item, is then deactivated; Cook B is a
    # different active Cook.
    dish = await _create_available_dish(client, db_session, name="Deactivated Cook Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=57)
    item = await _add_item(client, order["id"], dish["id"])
    cook_a = await _login_as_cook(client, db_session, "cook-a-deactivated")
    pick_up = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    assert pick_up.status_code == 200
    assert pick_up.json()["cook_id"] == cook_a.id

    db_cook_a = await db_session.get(User, cook_a.id)
    db_cook_a.is_active = False
    await db_session.commit()
    await _login_as_cook(client, db_session, "cook-b-active")

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")

    # Assert: attribution is not an access lock, cook_id stays cook_a's.
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["cook_id"] == cook_a.id


@pytest.mark.asyncio
async def test_pick_up_below_available_stock_still_succeeds_and_is_not_floor_capped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: current_stock less than the Recipe requires.
    dish, ingredient = await _create_available_dish_with_ingredient(
        client,
        db_session,
        name="Below Stock Dish",
        ingredient_stock="0.200",
        ingredient_threshold="0.100",
        recipe_quantity="0.500",
    )
    order, _waiter, _table = await _open_table(client, db_session, table_number=58)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "below-stock-cook")

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")

    # Assert: succeeds, and current_stock is not clamped at zero (AD-16).
    assert response.status_code == 200
    assert response.json()["status"] == "in_preparation"
    db_session.expire_all()
    updated_ingredient = await db_session.get(Ingredient, ingredient)
    assert updated_ingredient.current_stock == Decimal("-0.300")


@pytest.mark.asyncio
async def test_waiter_and_warehouse_manager_cannot_pick_up_or_mark_ready(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Role Guard Dish")
    order, waiter, _table = await _open_table(client, db_session, table_number=59)
    item = await _add_item(client, order["id"], dish["id"])

    # Act/Assert: the Waiter who opened the table cannot pick up.
    await _login(client, waiter.username)
    waiter_pick_up = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    assert waiter_pick_up.status_code == 403

    # Act/Assert: warehouse_manager cannot pick up or mark ready either.
    await _create_user(db_session, "role-guard-wm", UserRole.warehouse_manager)
    await _login(client, "role-guard-wm")
    wm_pick_up = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    wm_mark_ready = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")
    assert wm_pick_up.status_code == 403
    assert wm_mark_ready.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_pick_up_and_mark_ready(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Admin Pickup Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=60)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_admin(client, db_session, "pickup-admin")

    # Act
    pick_up = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    mark_ready = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")

    # Assert
    assert pick_up.status_code == 200
    assert mark_ready.status_code == 200
    assert mark_ready.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_unauthenticated_cannot_pick_up_or_mark_ready(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Unauth Pickup Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=61)
    item = await _add_item(client, order["id"], dish["id"])
    client.cookies.clear()

    # Act
    pick_up = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    mark_ready = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")

    # Assert
    assert pick_up.status_code == 401
    assert mark_ready.status_code == 401


@pytest.mark.asyncio
async def test_pick_up_and_mark_ready_on_a_nonexistent_item_are_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    order, _waiter, _table = await _open_table(client, db_session, table_number=62)
    await _login_as_cook(client, db_session, "not-found-cook")

    # Act
    pick_up = await client.post(f"/api/orders/{order['id']}/items/999999/pick-up")
    mark_ready = await client.post(f"/api/orders/{order['id']}/items/999999/mark-ready")

    # Assert
    assert pick_up.status_code == 404
    assert mark_ready.status_code == 404


@pytest.mark.asyncio
async def test_pick_up_on_an_item_belonging_to_a_different_order_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Wrong Order Dish")
    order_a, _waiter_a, _table_a = await _open_table(client, db_session, table_number=63)
    order_b, _waiter_b, _table_b = await _open_table(client, db_session, table_number=64)
    item = await _add_item(client, order_a["id"], dish["id"])
    await _login_as_cook(client, db_session, "wrong-order-cook")

    # Act
    response = await client.post(f"/api/orders/{order_b['id']}/items/{item['id']}/pick-up")

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_race_between_two_pick_ups_only_one_succeeds_and_deducts_once(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: the item is pending when this request's read step runs, but a
    # second request picks it up strictly between that read and this
    # request's guarded UPDATE (trap 18's "a real concurrency test must
    # change the state between the service's read and its write").
    dish, ingredient = await _create_available_dish_with_ingredient(client, db_session, name="Race Pickup Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=65)
    item = await _add_item(client, order["id"], dish["id"])
    cook = await _login_as_cook(client, db_session, "race-pickup-cook")

    original_get_item = OrderService._get_item

    async def get_item_then_pick_up(self, db, actor, requested_order_id, requested_item_id):
        loaded = await original_get_item(self, db, actor, requested_order_id, requested_item_id)
        assert loaded.status is OrderItemStatus.pending
        racing = await db_session.get(OrderItem, requested_item_id)
        racing.status = OrderItemStatus.in_preparation
        racing.cook_id = cook.id
        await db_session.commit()
        return loaded

    monkeypatch.setattr(OrderService, "_get_item", get_item_then_pick_up)

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")

    # Assert
    assert response.status_code == 409

    # Assert: the guarded UPDATE's rowcount hit 0 before any deduction was
    # attempted (the guard runs first, AD-6), so the racing write, not this
    # request, is the only thing that ever touched the item's status, and
    # stock is completely untouched by either.
    monkeypatch.undo()
    db_session.expire_all()
    updated_ingredient = await db_session.get(Ingredient, ingredient)
    assert updated_ingredient.current_stock == Decimal("10.000")
    movements = await db_session.execute(select(StockMovement).where(StockMovement.ingredient_id == ingredient))
    assert len(movements.scalars().all()) == 0
