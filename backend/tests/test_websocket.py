import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
import uvicorn
import websockets
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

import api.websocket as websocket_module
from constants import SETTINGS
from data_models import Category, Dish, Ingredient, RecipeIngredient, RestaurantTable, TableStatus, Unit, User, UserRole
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
async def test_missing_cookie_is_rejected_before_accept() -> None:
    # Act / Assert
    with TestClient(app, base_url="https://test") as client:
        with pytest.raises(WebSocketDisconnect) as rejection:
            with client.websocket_connect("/api/ws", headers={"origin": _ALLOWED_ORIGIN}):
                pass
    assert rejection.value.code == _POLICY_VIOLATION


@pytest.mark.asyncio
async def test_expired_token_is_rejected_before_accept(db_session) -> None:
    # Arrange
    user = await _create_user(db_session, "ws_expired")
    secret = load_config(SETTINGS.CONFIG_PATH)["auth"]["secret_key"]
    expired_token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        secret,
        algorithm="HS256",
    )

    # Act / Assert
    with TestClient(app, base_url="https://test") as client:
        headers = {"origin": _ALLOWED_ORIGIN, **_cookie_header(expired_token)}
        with pytest.raises(WebSocketDisconnect) as rejection:
            with client.websocket_connect("/api/ws", headers=headers):
                pass
    assert rejection.value.code == _POLICY_VIOLATION


@pytest.mark.asyncio
async def test_token_signed_with_wrong_key_is_rejected_before_accept(db_session) -> None:
    # Arrange
    user = await _create_user(db_session, "ws_forged")
    forged_token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "not-the-real-signing-key",
        algorithm="HS256",
    )

    # Act / Assert
    with TestClient(app, base_url="https://test") as client:
        headers = {"origin": _ALLOWED_ORIGIN, **_cookie_header(forged_token)}
        with pytest.raises(WebSocketDisconnect) as rejection:
            with client.websocket_connect("/api/ws", headers=headers):
                pass
    assert rejection.value.code == _POLICY_VIOLATION


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
async def test_broadcast_delivered_within_two_seconds(db_session) -> None:
    # Arrange
    await _create_user(db_session, "ws_broadcast")

    async with _running_server() as port:
        token = await _login_over_http(port, "ws_broadcast")

        # Act
        async with await _connect(port, token) as ws:
            realtime_service = await container.realtime_service()
            await realtime_service.broadcast([UserRole.cook], "test.smoke", {"ok": True})

            # Assert
            message = await asyncio.wait_for(ws.recv(), timeout=2)
            assert json.loads(message) == {"event": "test.smoke", "payload": {"ok": True}}


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
async def test_broadcast_reaches_every_targeted_role(db_session) -> None:
    # Arrange
    await _create_user(db_session, "ws_multi_cook", role=UserRole.cook)
    await _create_user(db_session, "ws_multi_waiter", role=UserRole.waiter)

    async with _running_server() as port:
        cook_token = await _login_over_http(port, "ws_multi_cook")
        waiter_token = await _login_over_http(port, "ws_multi_waiter")

        async with await _connect(port, cook_token) as cook_ws:
            async with await _connect(port, waiter_token) as waiter_ws:
                # Act: one emission, two audiences (AC4).
                realtime_service = await container.realtime_service()
                await realtime_service.broadcast(
                    [UserRole.cook, UserRole.waiter], "order.item_status_changed", {"id": 7}
                )

                # Assert
                expected = {"event": "order.item_status_changed", "payload": {"id": 7}}
                assert json.loads(await asyncio.wait_for(cook_ws.recv(), timeout=2)) == expected
                assert json.loads(await asyncio.wait_for(waiter_ws.recv(), timeout=2)) == expected


@pytest.mark.asyncio
async def test_second_connection_for_a_user_replaces_the_first(db_session) -> None:
    # Arrange
    await _create_user(db_session, "ws_single")

    async with _running_server() as port:
        token = await _login_over_http(port, "ws_single")
        first = await _connect(port, token)
        try:
            # Act: the same session opens a second socket.
            async with await _connect(port, token) as second:
                # Assert: the first is closed, and only the second is delivered to.
                with pytest.raises(ConnectionClosed):
                    await asyncio.wait_for(first.recv(), timeout=2)

                realtime_service = await container.realtime_service()
                await realtime_service.broadcast([UserRole.cook], "test.single", {"ok": True})
                message = await asyncio.wait_for(second.recv(), timeout=2)
                assert json.loads(message) == {"event": "test.single", "payload": {"ok": True}}
        finally:
            # The server already closed its end when the second connection registered;
            # this just releases the client-side handle so it cannot keep the server's
            # graceful shutdown (which waits for every connection to close) waiting.
            await first.close()


@pytest.mark.asyncio
async def test_binary_frame_does_not_break_the_connection(db_session) -> None:
    # Arrange
    await _create_user(db_session, "ws_binary")

    async with _running_server() as port:
        token = await _login_over_http(port, "ws_binary")

        async with await _connect(port, token) as ws:
            # Act: the client is never supposed to send, but a stray binary frame
            # must not fault the handler (receive_text would raise KeyError on it).
            await ws.send(b"\x00\x01\x02")
            await asyncio.sleep(0.2)

            # Assert: still connected and still receiving.
            realtime_service = await container.realtime_service()
            await realtime_service.broadcast([UserRole.cook], "test.after_binary", {"ok": True})
            message = await asyncio.wait_for(ws.recv(), timeout=2)
            assert json.loads(message) == {"event": "test.after_binary", "payload": {"ok": True}}


@pytest.mark.asyncio
async def test_connection_is_closed_once_its_session_stops_verifying(db_session, monkeypatch) -> None:
    # Arrange: re-verify almost immediately rather than on the production interval.
    monkeypatch.setattr(websocket_module, "REVERIFY_INTERVAL_SECONDS", 0.2)
    user = await _create_user(db_session, "ws_revoked")

    async with _running_server() as port:
        token = await _login_over_http(port, "ws_revoked")

        async with await _connect(port, token) as ws:
            # Act: deactivate the account out from under the open connection.
            user.is_active = False
            db_session.add(user)
            await db_session.commit()

            # Assert: the socket is closed by the re-verification tick, not left open.
            with pytest.raises(ConnectionClosed) as closed:
                await asyncio.wait_for(ws.recv(), timeout=5)
            assert closed.value.rcvd.code == _POLICY_VIOLATION


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

                        # Assert: Story 5.1 widened this event to also reach the Kitchen
                        # Display, so a connected Cook now receives the identical payload,
                        # not nothing.
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
async def test_marking_an_item_ready_broadcasts_order_item_status_changed_with_no_alert(
    db_session,
) -> None:
    # Arrange
    table = RestaurantTable(table_number=5, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="Caesar Salad",
        price="9.00",
        category_id=category.id,
        prep_time_minutes=10,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    await _create_user(db_session, "ws_ready_waiter", role=UserRole.waiter)
    await _create_user(db_session, "ws_ready_cook", role=UserRole.cook)
    await _create_user(db_session, "ws_ready_wm", role=UserRole.warehouse_manager)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_ready_waiter")
        cook_token = await _login_over_http(port, "ws_ready_cook")
        wm_token = await _login_over_http(port, "ws_ready_wm")

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

            http_client.cookies.set(COOKIE_NAME, cook_token)
            pick_up_response = await http_client.post(f"/api/orders/{order_id}/items/{item_id}/pick-up")
            assert pick_up_response.status_code == 200

            async with await _connect(port, waiter_token) as waiter_ws:
                async with await _connect(port, cook_token) as cook_ws:
                    async with await _connect(port, wm_token) as wm_ws:
                        # Act
                        ready_response = await http_client.post(
                            f"/api/orders/{order_id}/items/{item_id}/mark-ready"
                        )
                        assert ready_response.status_code == 200

                        # Assert
                        waiter_message = await asyncio.wait_for(waiter_ws.recv(), timeout=2)
                        parsed = json.loads(waiter_message)
                        assert parsed["event"] == "order.item_status_changed"
                        assert parsed["payload"]["status"] == "ready"

                        cook_message = await asyncio.wait_for(cook_ws.recv(), timeout=2)
                        assert json.loads(cook_message) == parsed

                        # Assert: mark-ready never touches stock, no alert broadcast.
                        with pytest.raises(asyncio.TimeoutError):
                            await asyncio.wait_for(wm_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_unserializable_payload_does_not_unsubscribe_the_client(db_session) -> None:
    # Arrange
    await _create_user(db_session, "ws_bad_payload")

    async with _running_server() as port:
        token = await _login_over_http(port, "ws_bad_payload")

        async with await _connect(port, token) as ws:
            realtime_service = await container.realtime_service()

            # Act: a sender-side bug, not a dead client.
            await realtime_service.broadcast(
                [UserRole.cook], "test.bad", {"when": datetime.now(timezone.utc)}
            )

            # Assert: the connection survives and still receives the next good event.
            await realtime_service.broadcast([UserRole.cook], "test.good", {"ok": True})
            message = await asyncio.wait_for(ws.recv(), timeout=2)
            assert json.loads(message) == {"event": "test.good", "payload": {"ok": True}}


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


@pytest.mark.asyncio
async def test_a_movement_that_does_not_cross_threshold_broadcasts_nothing(db_session) -> None:
    # Arrange: comfortably above threshold both before and after.
    ingredient = Ingredient(name="Vanilla", unit=Unit.kg, current_stock="10.000", min_stock_threshold="1.000")
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    await _create_user(db_session, "ws_no_cross_wm", role=UserRole.warehouse_manager)

    async with _running_server() as port:
        wm_token = await _login_over_http(port, "ws_no_cross_wm")

        async with await _connect(port, wm_token) as wm_ws:
            # Act
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
                http_client.cookies.set(COOKIE_NAME, wm_token)
                response = await http_client.post(
                    f"/api/inventory/ingredients/{ingredient.id}/movements",
                    json={"movement_type": "purchase", "quantity": "5.000"},
                )
            assert response.status_code == 201

            # Assert: no crossing, nothing broadcast.
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(wm_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_a_second_movement_while_already_in_shortage_broadcasts_nothing(db_session) -> None:
    # Arrange: already below threshold before this test's own movement lands.
    ingredient = Ingredient(name="Cardamom", unit=Unit.kg, current_stock="1.000", min_stock_threshold="3.000")
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    await _create_user(db_session, "ws_already_low_wm", role=UserRole.warehouse_manager)

    async with _running_server() as port:
        wm_token = await _login_over_http(port, "ws_already_low_wm")

        async with await _connect(port, wm_token) as wm_ws:
            # Act: still below threshold after, no crossing.
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
                http_client.cookies.set(COOKIE_NAME, wm_token)
                response = await http_client.post(
                    f"/api/inventory/ingredients/{ingredient.id}/movements",
                    json={"movement_type": "waste", "quantity": "0.500"},
                )
            assert response.status_code == 201

            # Assert
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(wm_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_a_purchase_that_reduces_but_does_not_clear_a_shortage_broadcasts_nothing(db_session) -> None:
    # Arrange: already below threshold before this test's own movement lands.
    # The symmetric case to test_a_second_movement_while_already_in_shortage_broadcasts_nothing
    # above, but with an increasing movement instead of a decreasing one.
    ingredient = Ingredient(name="Fennel", unit=Unit.kg, current_stock="0.500", min_stock_threshold="3.000")
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    await _create_user(db_session, "ws_reduces_shortage_wm", role=UserRole.warehouse_manager)

    async with _running_server() as port:
        wm_token = await _login_over_http(port, "ws_reduces_shortage_wm")

        async with await _connect(port, wm_token) as wm_ws:
            # Act: still below threshold after (0.500 + 1.000 = 1.500, threshold 3.000), no crossing.
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
                http_client.cookies.set(COOKIE_NAME, wm_token)
                response = await http_client.post(
                    f"/api/inventory/ingredients/{ingredient.id}/movements",
                    json={"movement_type": "purchase", "quantity": "1.000"},
                )
            assert response.status_code == 201

            # Assert
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(wm_ws.recv(), timeout=0.5)
