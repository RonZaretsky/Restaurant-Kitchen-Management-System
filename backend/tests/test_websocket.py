import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
import uvicorn
import websockets
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from constants import SETTINGS
from data_models import (
    Category,
    Dish,
    Ingredient,
    RecipeIngredient,
    RestaurantTable,
    TableStatus,
    Unit,
    User,
    UserRole,
)
from main import app, container
from services.auth_service import COOKIE_NAME, AuthService
from utils import load_config

_PASSWORD = "correct-horse-battery-staple"
_ALLOWED_ORIGIN = load_config(SETTINGS.CONFIG_PATH)["cors"]["allow_origin"]
_POLICY_VIOLATION = 1008
_SERVER_START_TIMEOUT = 10


async def _create_user(
    db_session, username: str, role: UserRole = UserRole.cook
) -> User:
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


def _cookie_header(token: str) -> dict:
    return {"cookie": f"{COOKIE_NAME}={token}"}


def _login(client: TestClient, username: str) -> str:
    client.post("/api/auth/login", json={"username": username, "password": _PASSWORD})
    token = client.cookies.get(COOKIE_NAME)
    # Guards every test below: without this, a broken login turns the cookie into
    # the literal string "None", and the rejection tests would pass for the wrong reason.
    assert token, "login did not set a session cookie"
    return token


@asynccontextmanager
async def _running_server():
    # A real uvicorn.Server bound to an ephemeral port, run as a task in this test's own
    # event loop. TestClient's websocket_connect runs the ASGI app in a separate thread
    # with its own event loop, which would make a broadcast call from a test race the
    # connection registry across two loops; a real server sharing this loop avoids that.
    #
    # lifespan="on" is deliberate, and symmetric on purpose: each test's server both
    # initialises and tears down container.init_resources()/shutdown_resources() itself,
    # exactly once. The earlier version of this test left resources initialised but never
    # torn down between tests, which pinned the database engine to a pytest-asyncio event
    # loop that a later test's own event loop had already replaced -- surfacing as
    # asyncpg's "another operation is in progress" in whichever test ran next.
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(_SERVER_START_TIMEOUT):
            while not server.started:
                await asyncio.sleep(0.01)
        yield server.servers[0].sockets[0].getsockname()[1]
    finally:
        server.should_exit = True
        # Bounded, so a server that fails to shut down fails the suite rather than hanging it.
        async with asyncio.timeout(_SERVER_START_TIMEOUT):
            await server_task


async def _connect(port: int, token: str):
    return await websockets.connect(
        f"ws://127.0.0.1:{port}/api/ws",
        origin=_ALLOWED_ORIGIN,
        additional_headers=_cookie_header(token),
    )


async def _login_over_http(port: int, username: str) -> str:
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
        response = await http_client.post(
            "/api/auth/login", json={"username": username, "password": _PASSWORD}
        )
    token = response.cookies.get(COOKIE_NAME)
    assert token, "login did not set a session cookie"
    return token


@pytest.mark.asyncio
async def test_valid_session_connects(db_session) -> None:
    # Arrange
    user = await _create_user(db_session, "ws_valid")

    with TestClient(app, base_url="https://test") as client:
        token = _login(client, "ws_valid")

        # Act
        headers = {"origin": _ALLOWED_ORIGIN, **_cookie_header(token)}
        with client.websocket_connect("/api/ws", headers=headers):
            # Assert: the handshake completed and the connection is actually
            # registered, rather than merely "did not raise".
            registry = await container.connection_registry()
            assert user.id in registry._connections


@pytest.mark.asyncio
async def test_mismatched_origin_is_rejected_before_accept(db_session) -> None:
    # Arrange
    # CORSMiddleware does not inspect the websocket ASGI scope at all, so this
    # rejection is entirely the route's own manual check, not a side effect of
    # the middleware stack.
    await _create_user(db_session, "ws_bad_origin")

    with TestClient(app, base_url="https://test") as client:
        token = _login(client, "ws_bad_origin")

        # Act / Assert
        headers = {"origin": "http://evil.example", **_cookie_header(token)}
        with pytest.raises(WebSocketDisconnect) as rejection:
            with client.websocket_connect("/api/ws", headers=headers):
                pass
    assert rejection.value.code == _POLICY_VIOLATION


@pytest.mark.asyncio
async def test_broadcast_is_scoped_to_the_targeted_role(db_session) -> None:
    # Arrange: one cook and one waiter, both connected.
    await _create_user(db_session, "ws_scope_cook", role=UserRole.cook)
    await _create_user(db_session, "ws_scope_waiter", role=UserRole.waiter)

    async with _running_server() as port:
        cook_token = await _login_over_http(port, "ws_scope_cook")
        waiter_token = await _login_over_http(port, "ws_scope_waiter")

        async with await _connect(port, cook_token) as cook_ws:
            async with await _connect(port, waiter_token) as waiter_ws:
                # Act: target cooks only.
                realtime_service = await container.realtime_service()
                await realtime_service.broadcast([UserRole.cook], "test.scoped", {"n": 1})

                # Assert: the cook receives it, the waiter does not.
                message = await asyncio.wait_for(cook_ws.recv(), timeout=2)
                assert json.loads(message) == {"event": "test.scoped", "payload": {"n": 1}}
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(waiter_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_opening_a_table_broadcasts_table_status_changed(db_session) -> None:
    # Arrange: a Table created directly via the DB session, same shortcut this
    # file's own User creation already takes, so no admin-login/HTTP round trip
    # is needed just to set up fixture data.
    table = RestaurantTable(table_number=1, capacity=4, status=TableStatus.available)
    db_session.add(table)
    await db_session.commit()
    await db_session.refresh(table)
    await _create_user(db_session, "ws_table_status", role=UserRole.waiter)
    await _create_user(db_session, "ws_table_status_cook", role=UserRole.cook)

    async with _running_server() as port:
        token = await _login_over_http(port, "ws_table_status")
        cook_token = await _login_over_http(port, "ws_table_status_cook")

        async with await _connect(port, token) as ws:
            async with await _connect(port, cook_token) as cook_ws:
                # Act
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
                    http_client.cookies.set(COOKIE_NAME, token)
                    response = await http_client.post(f"/api/orders/tables/{table.id}/open")
                assert response.status_code == 201

                # Assert
                message = await asyncio.wait_for(ws.recv(), timeout=2)
                assert json.loads(message) == {
                    "event": "table.status_changed",
                    "payload": {"table_id": table.id, "status": "occupied"},
                }

                # Assert: the event is Waiter-scoped, a Cook receives nothing.
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(cook_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_adding_an_order_item_broadcasts_order_item_added(db_session) -> None:
    # Arrange
    table = RestaurantTable(table_number=2, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="Margherita",
        price="12.50",
        category_id=category.id,
        prep_time_minutes=15,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    await _create_user(db_session, "ws_item_added", role=UserRole.waiter)
    await _create_user(db_session, "ws_item_added_cook", role=UserRole.cook)
    await _create_user(db_session, "ws_item_added_wm", role=UserRole.warehouse_manager)

    async with _running_server() as port:
        token = await _login_over_http(port, "ws_item_added")
        cook_token = await _login_over_http(port, "ws_item_added_cook")
        wm_token = await _login_over_http(port, "ws_item_added_wm")

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
            http_client.cookies.set(COOKIE_NAME, token)
            open_response = await http_client.post(f"/api/orders/tables/{table.id}/open")
            assert open_response.status_code == 201
            order_id = open_response.json()["id"]

            async with await _connect(port, token) as ws:
                async with await _connect(port, cook_token) as cook_ws:
                    async with await _connect(port, wm_token) as wm_ws:
                        # Act
                        add_response = await http_client.post(
                            f"/api/orders/{order_id}/items",
                            json={"dish_id": dish.id, "quantity": 2, "notes": "no onions"},
                        )
                        assert add_response.status_code == 201
                        item = add_response.json()

                        # Assert
                        message = await asyncio.wait_for(ws.recv(), timeout=2)
                        parsed = json.loads(message)
                        assert parsed["event"] == "order.item_added"
                        assert parsed["payload"]["id"] == item["id"]
                        assert parsed["payload"]["order_id"] == order_id
                        assert parsed["payload"]["dish_id"] == dish.id
                        assert parsed["payload"]["quantity"] == 2
                        assert parsed["payload"]["notes"] == "no onions"
                        assert parsed["payload"]["price_at_add"] == "12.50"

                        # Assert: this event also reaches the Kitchen Display, so a
                        # connected Cook receives the identical payload.
                        cook_message = await asyncio.wait_for(cook_ws.recv(), timeout=2)
                        assert json.loads(cook_message) == parsed

                        # Assert: still Role-scoped, not a blanket broadcast — a
                        # connected warehouse_manager receives nothing.
                        with pytest.raises(asyncio.TimeoutError):
                            await asyncio.wait_for(wm_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_picking_up_an_order_item_broadcasts_order_item_status_changed(db_session) -> None:
    # Arrange
    table = RestaurantTable(table_number=3, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="Margherita",
        price="12.50",
        category_id=category.id,
        prep_time_minutes=15,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    ingredient = Ingredient(name="Dough", unit=Unit.kg, current_stock="10.000", min_stock_threshold="1.000")
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    db_session.add(RecipeIngredient(dish_id=dish.id, ingredient_id=ingredient.id, unit=Unit.kg, quantity="0.500"))
    await db_session.commit()
    await _create_user(db_session, "ws_pickup_waiter", role=UserRole.waiter)
    await _create_user(db_session, "ws_pickup_cook", role=UserRole.cook)
    await _create_user(db_session, "ws_pickup_wm", role=UserRole.warehouse_manager)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_pickup_waiter")
        cook_token = await _login_over_http(port, "ws_pickup_cook")
        wm_token = await _login_over_http(port, "ws_pickup_wm")

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
            http_client.cookies.set(COOKIE_NAME, waiter_token)
            open_response = await http_client.post(f"/api/orders/tables/{table.id}/open")
            assert open_response.status_code == 201
            order_id = open_response.json()["id"]
            add_response = await http_client.post(
                f"/api/orders/{order_id}/items", json={"dish_id": dish.id, "quantity": 1}
            )
            assert add_response.status_code == 201
            item_id = add_response.json()["id"]

            async with await _connect(port, waiter_token) as waiter_ws:
                async with await _connect(port, cook_token) as cook_ws:
                    async with await _connect(port, wm_token) as wm_ws:
                        # Act
                        http_client.cookies.set(COOKIE_NAME, cook_token)
                        pick_up_response = await http_client.post(
                            f"/api/orders/{order_id}/items/{item_id}/pick-up"
                        )
                        assert pick_up_response.status_code == 200

                        # Assert: both Waiter and Cook receive the status change.
                        waiter_message = await asyncio.wait_for(waiter_ws.recv(), timeout=2)
                        parsed = json.loads(waiter_message)
                        assert parsed["event"] == "order.item_status_changed"
                        assert parsed["payload"]["id"] == item_id
                        assert parsed["payload"]["status"] == "in_preparation"

                        cook_message = await asyncio.wait_for(cook_ws.recv(), timeout=2)
                        assert json.loads(cook_message) == parsed

                        # Assert: not crossing threshold (10.000 - 0.500 stays above 1.000),
                        # so warehouse_manager receives nothing.
                        with pytest.raises(asyncio.TimeoutError):
                            await asyncio.wait_for(wm_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_picking_up_an_order_item_that_crosses_threshold_also_broadcasts_alerts_changed(
    db_session,
) -> None:
    # Arrange: stock only just above threshold, so a single pick-up crosses it.
    table = RestaurantTable(table_number=4, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="Truffle Risotto",
        price="22.00",
        category_id=category.id,
        prep_time_minutes=20,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    ingredient = Ingredient(name="Truffle", unit=Unit.kg, current_stock="1.200", min_stock_threshold="1.000")
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    db_session.add(RecipeIngredient(dish_id=dish.id, ingredient_id=ingredient.id, unit=Unit.kg, quantity="0.500"))
    await db_session.commit()
    await _create_user(db_session, "ws_cross_waiter", role=UserRole.waiter)
    await _create_user(db_session, "ws_cross_cook", role=UserRole.cook)
    await _create_user(db_session, "ws_cross_wm", role=UserRole.warehouse_manager)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_cross_waiter")
        cook_token = await _login_over_http(port, "ws_cross_cook")
        wm_token = await _login_over_http(port, "ws_cross_wm")

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
            http_client.cookies.set(COOKIE_NAME, waiter_token)
            open_response = await http_client.post(f"/api/orders/tables/{table.id}/open")
            assert open_response.status_code == 201
            order_id = open_response.json()["id"]
            add_response = await http_client.post(
                f"/api/orders/{order_id}/items", json={"dish_id": dish.id, "quantity": 1}
            )
            assert add_response.status_code == 201
            item_id = add_response.json()["id"]

            async with await _connect(port, wm_token) as wm_ws:
                # Act
                http_client.cookies.set(COOKIE_NAME, cook_token)
                pick_up_response = await http_client.post(f"/api/orders/{order_id}/items/{item_id}/pick-up")
                assert pick_up_response.status_code == 200

                # Assert: 1.200 - 0.500 = 0.700, now below 1.000, threshold crossed.
                message = await asyncio.wait_for(wm_ws.recv(), timeout=2)
                assert json.loads(message) == {
                    "event": "inventory.alerts_changed",
                    "payload": {"ingredient_id": ingredient.id},
                }


@pytest.mark.asyncio
async def test_a_movement_crossing_below_threshold_broadcasts_alerts_changed(db_session) -> None:
    # Arrange
    ingredient = Ingredient(name="Saffron", unit=Unit.kg, current_stock="5.000", min_stock_threshold="3.000")
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    await _create_user(db_session, "ws_alert_wm", role=UserRole.warehouse_manager)
    await _create_user(db_session, "ws_alert_cook", role=UserRole.cook)

    async with _running_server() as port:
        wm_token = await _login_over_http(port, "ws_alert_wm")
        cook_token = await _login_over_http(port, "ws_alert_cook")

        async with await _connect(port, wm_token) as wm_ws:
            async with await _connect(port, cook_token) as cook_ws:
                # Act
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
                    http_client.cookies.set(COOKIE_NAME, wm_token)
                    response = await http_client.post(
                        f"/api/inventory/ingredients/{ingredient.id}/movements",
                        json={"movement_type": "waste", "quantity": "3.000"},
                    )
                assert response.status_code == 201

                # Assert
                message = await asyncio.wait_for(wm_ws.recv(), timeout=2)
                assert json.loads(message) == {
                    "event": "inventory.alerts_changed",
                    "payload": {"ingredient_id": ingredient.id},
                }

                # Assert: warehouse_manager-scoped, a Cook (also permitted to read
                # /alerts, but not a UI consumer of it) receives nothing.
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(cook_ws.recv(), timeout=0.5)

