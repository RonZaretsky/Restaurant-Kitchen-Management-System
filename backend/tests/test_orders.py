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
    OrderStatus,
    RestaurantTable,
    StockMovement,
    TableStatus,
    Unit,
    User,
    UserRole,
)
from data_models.order import MAX_ORDER_ITEM_QUANTITY
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
async def test_admin_cannot_open_a_table(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    table = await _create_table(client, db_session)
    await _login_as_admin(client, db_session)

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
async def test_pick_up_below_available_stock_is_rejected_and_item_stays_pending(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: current_stock less than the Recipe requires. Reverses AD-16 (this batch's #5) —
    # the pick-up is now rejected cleanly rather than deducting past zero.
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

    # Assert: rejected, the item stays pending, and the ingredient's stock is untouched.
    assert response.status_code == 409
    assert response.json()["detail"] == "Not enough stock to prepare this item"
    db_session.expire_all()
    unchanged_item = await db_session.get(OrderItem, item["id"])
    assert unchanged_item.status is OrderItemStatus.pending
    updated_ingredient = await db_session.get(Ingredient, ingredient)
    assert updated_ingredient.current_stock == Decimal("0.200")
    movements = await db_session.execute(select(StockMovement).where(StockMovement.ingredient_id == ingredient))
    assert movements.scalars().all() == []


@pytest.mark.asyncio
async def test_cook_can_reject_a_pending_item_with_insufficient_stock(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: 3.000 in stock, 1.000 per portion -> 3 portions preparable, but 5 were ordered.
    dish, ingredient = await _create_available_dish_with_ingredient(
        client,
        db_session,
        name="Reject Insufficient Dish",
        ingredient_stock="3.000",
        ingredient_threshold="1.000",
        recipe_quantity="1.000",
    )
    order, _waiter, _table = await _open_table(client, db_session, table_number=70)
    item = await _add_item(client, order["id"], dish["id"], quantity=5)
    await _login_as_cook(client, db_session, "reject-insufficient-cook")

    # Act
    response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/reject")

    # Assert: rejected with a message stating the actual max preparable amount, no stock touched.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["reject_reason"] == "Only 3 of 5 requested could be prepared (insufficient stock)."
    updated_ingredient = await db_session.get(Ingredient, ingredient)
    assert updated_ingredient.current_stock == Decimal("3.000")
    movements = await db_session.execute(select(StockMovement).where(StockMovement.ingredient_id == ingredient))
    assert movements.scalars().all() == []


@pytest.mark.asyncio
async def test_waiter_and_warehouse_manager_cannot_reject(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Reject Role Guard Dish")
    order, waiter, _table = await _open_table(client, db_session, table_number=75)
    item = await _add_item(client, order["id"], dish["id"])

    # Act/Assert: the Waiter who opened the table cannot reject.
    await _login(client, waiter.username)
    waiter_reject = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/reject")
    assert waiter_reject.status_code == 403

    # Act/Assert: warehouse_manager cannot reject either.
    await _create_user(db_session, "reject-role-guard-wm", UserRole.warehouse_manager)
    await _login(client, "reject-role-guard-wm")
    wm_reject = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/reject")
    assert wm_reject.status_code == 403


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


# --- Story 5.3: Order.status derivation (FR-12) -----------------------------------------------


@pytest.mark.asyncio
async def test_order_status_round_trips_pending_to_in_preparation_and_back(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: a freshly opened Order is pending by default (zero items). Adding one pending
    # item is not "zero non-cancelled items" and not "every item ready", so the aggregate is
    # in_preparation (AC1's "anything else" bucket, exercised here with a single pending item,
    # not just a mix). Cancelling that same item brings the non-cancelled count back to zero,
    # returning the Order to pending (AC3) — not "stuck" at in_preparation, proving the
    # recompute actually re-derives on every change rather than only moving forward.
    dish = await _create_available_dish(client, db_session, name="Round Trip Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=70)

    db_session.expire_all()
    assert (await db_session.get(Order, order["id"])).status is OrderStatus.pending

    # Act: add the item.
    item = await _add_item(client, order["id"], dish["id"])

    # Assert
    db_session.expire_all()
    assert (await db_session.get(Order, order["id"])).status is OrderStatus.in_preparation

    # Act: cancel it back out.
    cancel_response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")
    assert cancel_response.status_code == 200

    # Assert
    db_session.expire_all()
    assert (await db_session.get(Order, order["id"])).status is OrderStatus.pending


@pytest.mark.asyncio
async def test_order_reaches_ready_only_once_every_item_is_ready(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: two items on one Order.
    dish = await _create_available_dish(client, db_session, name="All Ready Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=71)
    item_one = await _add_item(client, order["id"], dish["id"])
    item_two = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "order-ready-cook")

    # Act: bring only the first item to ready.
    pick_up_one = await client.post(f"/api/orders/{order['id']}/items/{item_one['id']}/pick-up")
    assert pick_up_one.status_code == 200
    ready_one = await client.post(f"/api/orders/{order['id']}/items/{item_one['id']}/mark-ready")
    assert ready_one.status_code == 200

    # Assert: one ready, one still pending — the mix case (AC1), not ready yet.
    db_session.expire_all()
    assert (await db_session.get(Order, order["id"])).status is OrderStatus.in_preparation

    # Act: bring the second item to ready too.
    pick_up_two = await client.post(f"/api/orders/{order['id']}/items/{item_two['id']}/pick-up")
    assert pick_up_two.status_code == 200
    ready_two = await client.post(f"/api/orders/{order['id']}/items/{item_two['id']}/mark-ready")
    assert ready_two.status_code == 200

    # Assert: both non-cancelled items are ready — the Order now reads ready (AC2).
    db_session.expire_all()
    assert (await db_session.get(Order, order["id"])).status is OrderStatus.ready


@pytest.mark.asyncio
async def test_adding_a_new_item_pulls_a_ready_order_back_to_in_preparation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: a single-item Order taken all the way to ready.
    dish = await _create_available_dish(client, db_session, name="Pulled Back Dish")
    order, waiter, _table = await _open_table(client, db_session, table_number=73)
    # Captured now, as a plain str, not read off the ORM object after the expire_all() calls
    # below: an attribute access on an ORM instance post-expire triggers a synchronous
    # lazy-load an AsyncSession cannot perform outside an explicit await (MissingGreenlet).
    waiter_username = waiter.username
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "pulled-back-cook")
    pick_up = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")
    assert pick_up.status_code == 200
    mark_ready = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")
    assert mark_ready.status_code == 200

    db_session.expire_all()
    assert (await db_session.get(Order, order["id"])).status is OrderStatus.ready

    # Act: the Waiter adds a brand-new pending item to the same, already-ready Order.
    await _login(client, waiter_username)
    await _add_item(client, order["id"], dish["id"])

    # Assert: the new pending item pulls the aggregate back down (AC1/FR-12) — a ready Order is
    # not "sticky", it re-derives on every item-set change, including an addition.
    db_session.expire_all()
    assert (await db_session.get(Order, order["id"])).status is OrderStatus.in_preparation


@pytest.mark.asyncio
async def test_get_open_orders_lists_every_non_closed_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: two open Orders on two different Tables.
    order_a, waiter, _table_a = await _open_table(client, db_session, table_number=74)
    order_b, _waiter_b, _table_b = await _open_table(client, db_session, table_number=75)

    # Act
    await _login(client, waiter.username)
    response = await client.get("/api/orders")

    # Assert
    assert response.status_code == 200
    order_ids = {order["id"] for order in response.json()}
    assert order_a["id"] in order_ids
    assert order_b["id"] in order_ids


@pytest.mark.asyncio
async def test_recompute_does_not_touch_a_closed_order(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange: an Order forced to `closed` directly with a still-pending item (no ordinary code
    # path can produce this combination — closed is genuinely terminal). If
    # _recompute_order_status's closed no-op guard were ever broken, cancelling that item would
    # wrongly revert this Order back to `pending` (zero non-cancelled items left) instead of
    # leaving it untouched (code review finding, Story 5.3: this guard previously shipped with
    # zero test coverage). `served` is deliberately NOT covered by this same guard any more (this
    # batch's own fix, see the sibling test below) — closed is the only status recompute still
    # refuses to touch.
    dish = await _create_available_dish(client, db_session, name="Closed Guard Dish")
    order, waiter, _table = await _open_table(client, db_session, table_number=78)
    waiter_username = waiter.username
    item = await _add_item(client, order["id"], dish["id"])

    db_order = await db_session.get(Order, order["id"])
    db_order.status = OrderStatus.closed
    await db_session.commit()

    # Act
    await _login(client, waiter_username)
    cancel_response = await client.post(f"/api/orders/{order['id']}/items/{item['id']}/cancel")
    assert cancel_response.status_code == 200

    # Assert: still closed, not reverted to pending.
    db_session.expire_all()
    assert (await db_session.get(Order, order["id"])).status is OrderStatus.closed


@pytest.mark.asyncio
async def test_adding_an_item_to_a_served_order_reverts_it_to_in_preparation_and_it_reaches_the_kitchen(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: a real serve, through the actual API flow (not a forced DB write) — a manual-test
    # bug (this batch): a Waiter adding one more dish after the table was already served left the
    # Order silently stuck at `served`, which hid the brand-new pending item from the Kitchen
    # Display entirely (its board filters out every item of a served/closed Order).
    dish = await _create_available_dish(client, db_session, name="Post Serve Dish")
    order, waiter, _table = await _open_table(client, db_session, table_number=79)
    first_item = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "post-serve-cook")
    pick_up = await client.post(f"/api/orders/{order['id']}/items/{first_item['id']}/pick-up")
    assert pick_up.status_code == 200
    mark_ready = await client.post(f"/api/orders/{order['id']}/items/{first_item['id']}/mark-ready")
    assert mark_ready.status_code == 200
    await _login(client, waiter.username)
    serve_response = await client.post(f"/api/orders/{order['id']}/serve")
    assert serve_response.status_code == 200
    assert serve_response.json()["status"] == "served"

    # Act: the Waiter adds one more dish to the already-served Order.
    second_item = await _add_item(client, order["id"], dish["id"])

    # Assert: the Order is active again (not stuck at served)...
    order_response = await client.get(f"/api/orders/tables/{order['table_id']}")
    assert order_response.status_code == 200
    assert order_response.json()["status"] == "in_preparation"

    # ...and the new item is now visible to the kitchen (the bug being fixed).
    await _login_as_cook(client, db_session, "post-serve-cook-2")
    kitchen_response = await client.get("/api/kitchen/items")
    assert kitchen_response.status_code == 200
    kitchen_item_ids = {item["id"] for item in kitchen_response.json()}
    assert second_item["id"] in kitchen_item_ids


@pytest.mark.asyncio
async def test_marking_a_ready_order_served_succeeds(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Serve Ready Dish")
    order, waiter, _table = await _open_table(client, db_session, table_number=80)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "serve-ready-cook")
    assert (await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")).status_code == 200
    assert (await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")).status_code == 200
    await _login(client, waiter.username)

    # Act
    response = await client.post(f"/api/orders/{order['id']}/serve")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "served"


@pytest.mark.asyncio
async def test_marking_served_rejected_when_an_item_is_not_yet_ready(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    dish = await _create_available_dish(client, db_session, name="Serve Not Ready Dish")
    order, _waiter, _table = await _open_table(client, db_session, table_number=82)
    await _add_item(client, order["id"], dish["id"])

    # Act
    response = await client.post(f"/api/orders/{order['id']}/serve")

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, order is not ready to be served"
    db_session.expire_all()
    assert (await db_session.get(Order, order["id"])).status is OrderStatus.in_preparation


@pytest.mark.asyncio
async def test_closing_a_served_order_computes_the_total_and_frees_the_table(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: two items that end up ready (different price/quantity, so the sum is only correct
    # if both are actually included), plus a third item cancelled before serving, which must be
    # excluded from the total (AD-7, the epic's own literal wording).
    dish_a = await _create_available_dish(client, db_session, name="Close Total Dish A", price="12.50")
    dish_b = await _create_available_dish(client, db_session, name="Close Total Dish B", price="20.00")
    order, waiter, table = await _open_table(client, db_session, table_number=84)
    item_a = await _add_item(client, order["id"], dish_a["id"], quantity=2)
    item_b = await _add_item(client, order["id"], dish_b["id"], quantity=1)
    cancelled_item = await _add_item(client, order["id"], dish_a["id"], quantity=5)
    cancel_response = await client.post(f"/api/orders/{order['id']}/items/{cancelled_item['id']}/cancel")
    assert cancel_response.status_code == 200

    await _login_as_cook(client, db_session, "close-total-cook")
    for item in (item_a, item_b):
        assert (await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")).status_code == 200
        assert (await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")).status_code == 200

    await _login(client, waiter.username)
    serve_response = await client.post(f"/api/orders/{order['id']}/serve")
    assert serve_response.status_code == 200

    # Act
    response = await client.post(f"/api/orders/{order['id']}/close")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "closed"
    assert Decimal(body["total_amount"]) == Decimal("12.50") * 2 + Decimal("20.00") * 1
    assert body["closed_at"] is not None

    db_session.expire_all()
    updated_table = await db_session.get(RestaurantTable, table["id"])
    assert updated_table.status is TableStatus.available


@pytest.mark.asyncio
async def test_closing_an_order_that_is_not_yet_served_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: a ready Order (not yet marked served).
    dish = await _create_available_dish(client, db_session, name="Close Not Served Dish")
    order, waiter, table = await _open_table(client, db_session, table_number=85)
    item = await _add_item(client, order["id"], dish["id"])
    await _login_as_cook(client, db_session, "close-not-served-cook")
    assert (await client.post(f"/api/orders/{order['id']}/items/{item['id']}/pick-up")).status_code == 200
    assert (await client.post(f"/api/orders/{order['id']}/items/{item['id']}/mark-ready")).status_code == 200
    await _login(client, waiter.username)

    # Act
    response = await client.post(f"/api/orders/{order['id']}/close")

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, order is not served yet"
    db_session.expire_all()
    assert (await db_session.get(Order, order["id"])).total_amount is None
    updated_table = await db_session.get(RestaurantTable, table["id"])
    assert updated_table.status is TableStatus.occupied


@pytest.mark.asyncio
async def test_serve_and_close_role_coverage(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    order, waiter, _table = await _open_table(client, db_session, table_number=88)

    # Act/Assert: cook, admin, warehouse_manager all 403 on both routes (OrdersDep is
    # Waiter-only, no Admin fallback, matching every other route in this file gated on it).
    await _create_user(db_session, "serve-close-cook", UserRole.cook)
    await _login(client, "serve-close-cook")
    assert (await client.post(f"/api/orders/{order['id']}/serve")).status_code == 403
    assert (await client.post(f"/api/orders/{order['id']}/close")).status_code == 403

    await _login_as_admin(client, db_session, "serve-close-admin")
    assert (await client.post(f"/api/orders/{order['id']}/serve")).status_code == 403
    assert (await client.post(f"/api/orders/{order['id']}/close")).status_code == 403

    await _create_user(db_session, "serve-close-wm", UserRole.warehouse_manager)
    await _login(client, "serve-close-wm")
    assert (await client.post(f"/api/orders/{order['id']}/serve")).status_code == 403
    assert (await client.post(f"/api/orders/{order['id']}/close")).status_code == 403

    # Act/Assert: unauthenticated is rejected.
    client.cookies.clear()
    assert (await client.post(f"/api/orders/{order['id']}/serve")).status_code == 401
    assert (await client.post(f"/api/orders/{order['id']}/close")).status_code == 401

    # Act/Assert: the Waiter who owns the Order can still serve/close it.
    await _login(client, waiter.username)
    assert (await client.post(f"/api/orders/{order['id']}/serve")).status_code == 200
    assert (await client.post(f"/api/orders/{order['id']}/close")).status_code == 200

