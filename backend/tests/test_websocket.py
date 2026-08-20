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
from data_models import (
    Category,
    Dish,
    Ingredient,
    OrderItem,
    OrderItemStatus,
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
async def test_cancelling_an_order_item_broadcasts_order_item_status_changed(db_session) -> None:
    # Arrange: closes the gap Story 5.5 exists for — cancel_item never broadcast before this
    # story, so an already-open Kitchen Display never reflected a cancellation live (NFR-1).
    table = RestaurantTable(table_number=11, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="Cancel Broadcast Dish",
        price="9.00",
        category_id=category.id,
        prep_time_minutes=10,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    await _create_user(db_session, "ws_cancel_waiter", role=UserRole.waiter)
    await _create_user(db_session, "ws_cancel_cook", role=UserRole.cook)
    await _create_user(db_session, "ws_cancel_wm", role=UserRole.warehouse_manager)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_cancel_waiter")
        cook_token = await _login_over_http(port, "ws_cancel_cook")
        wm_token = await _login_over_http(port, "ws_cancel_wm")

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
                        cancel_response = await http_client.post(
                            f"/api/orders/{order_id}/items/{item_id}/cancel"
                        )
                        assert cancel_response.status_code == 200

                        # Assert: both Waiter and Cook receive the status change.
                        waiter_message = await asyncio.wait_for(waiter_ws.recv(), timeout=2)
                        parsed = json.loads(waiter_message)
                        assert parsed["event"] == "order.item_status_changed"
                        assert parsed["payload"]["id"] == item_id
                        assert parsed["payload"]["status"] == "cancelled"

                        cook_message = await asyncio.wait_for(cook_ws.recv(), timeout=2)
                        assert json.loads(cook_message) == parsed

                        # Assert: cancelling this Order's only item drops it to zero non-cancelled
                        # items, which is a genuine aggregate change too (in_preparation ->
                        # pending, FR-12) — the Waiter also receives order.status_changed right
                        # after, with the correct order id and new status, not just any payload.
                        waiter_order_message = await asyncio.wait_for(waiter_ws.recv(), timeout=2)
                        order_parsed = json.loads(waiter_order_message)
                        assert order_parsed["event"] == "order.status_changed"
                        assert order_parsed["payload"]["id"] == order_id
                        assert order_parsed["payload"]["status"] == "pending"
                        with pytest.raises(asyncio.TimeoutError):
                            await asyncio.wait_for(cook_ws.recv(), timeout=0.5)

                        # Assert: order.item_status_changed and order.status_changed are both
                        # waiter/cook-only — a connected warehouse_manager receives neither.
                        with pytest.raises(asyncio.TimeoutError):
                            await asyncio.wait_for(wm_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_editing_an_order_item_broadcasts_order_item_status_changed(db_session) -> None:
    # Arrange
    table = RestaurantTable(table_number=12, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="Edit Broadcast Dish",
        price="9.00",
        category_id=category.id,
        prep_time_minutes=10,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    await _create_user(db_session, "ws_edit_waiter", role=UserRole.waiter)
    await _create_user(db_session, "ws_edit_cook", role=UserRole.cook)
    await _create_user(db_session, "ws_edit_wm", role=UserRole.warehouse_manager)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_edit_waiter")
        cook_token = await _login_over_http(port, "ws_edit_cook")
        wm_token = await _login_over_http(port, "ws_edit_wm")

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
                        edit_response = await http_client.patch(
                            f"/api/orders/{order_id}/items/{item_id}",
                            json={"quantity": 3, "notes": "extra spicy"},
                        )
                        assert edit_response.status_code == 200

                        # Assert: both Waiter and Cook receive the status change, no
                        # order.status_changed follows (edit never touches an item's status, so
                        # the aggregate cannot have changed).
                        waiter_message = await asyncio.wait_for(waiter_ws.recv(), timeout=2)
                        parsed = json.loads(waiter_message)
                        assert parsed["event"] == "order.item_status_changed"
                        assert parsed["payload"]["id"] == item_id
                        assert parsed["payload"]["quantity"] == 3
                        assert parsed["payload"]["notes"] == "extra spicy"

                        cook_message = await asyncio.wait_for(cook_ws.recv(), timeout=2)
                        assert json.loads(cook_message) == parsed

                        # Assert: nothing further arrives on either connected channel.
                        with pytest.raises(asyncio.TimeoutError):
                            await asyncio.wait_for(waiter_ws.recv(), timeout=0.5)
                        with pytest.raises(asyncio.TimeoutError):
                            await asyncio.wait_for(cook_ws.recv(), timeout=0.5)
                        with pytest.raises(asyncio.TimeoutError):
                            await asyncio.wait_for(wm_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_rejected_edit_broadcasts_nothing(db_session) -> None:
    # Arrange: an item already past pending (in_preparation), so edit_item's own guard rejects
    # the request before reaching the new broadcast call — pinning that the guard still runs
    # first, not just that it happens to today (review finding).
    table = RestaurantTable(table_number=13, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="Rejected Edit Dish",
        price="9.00",
        category_id=category.id,
        prep_time_minutes=10,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    await _create_user(db_session, "ws_rejected_edit_waiter", role=UserRole.waiter)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_rejected_edit_waiter")

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

            item_row = await db_session.get(OrderItem, item_id)
            item_row.status = OrderItemStatus.in_preparation
            await db_session.commit()

            async with await _connect(port, waiter_token) as waiter_ws:
                # Act
                edit_response = await http_client.patch(
                    f"/api/orders/{order_id}/items/{item_id}",
                    json={"quantity": 2, "notes": None},
                )
                assert edit_response.status_code == 409

                # Assert
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(waiter_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_rejected_cancel_broadcasts_nothing(db_session) -> None:
    # Arrange: an item already ready, so cancel_item's own guard rejects the request before
    # reaching the new broadcast call — same pinning purpose as the rejected-edit test above.
    table = RestaurantTable(table_number=14, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="Rejected Cancel Dish",
        price="9.00",
        category_id=category.id,
        prep_time_minutes=10,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    await _create_user(db_session, "ws_rejected_cancel_waiter", role=UserRole.waiter)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_rejected_cancel_waiter")

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

            item_row = await db_session.get(OrderItem, item_id)
            item_row.status = OrderItemStatus.ready
            await db_session.commit()

            async with await _connect(port, waiter_token) as waiter_ws:
                # Act
                cancel_response = await http_client.post(f"/api/orders/{order_id}/items/{item_id}/cancel")
                assert cancel_response.status_code == 409

                # Assert
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(waiter_ws.recv(), timeout=0.5)


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
async def test_picking_up_an_order_item_already_below_threshold_broadcasts_nothing(db_session) -> None:
    # Arrange: stock already below threshold before the pick-up, and stays
    # below after — was_low == is_low == True, no crossing (review finding,
    # Story 5.2: Task 7's own text requires both non-crossing cases tested,
    # not just "stays comfortably above").
    table = RestaurantTable(table_number=6, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="Already Low Dish",
        price="15.00",
        category_id=category.id,
        prep_time_minutes=10,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    ingredient = Ingredient(name="Saffron", unit=Unit.kg, current_stock="0.800", min_stock_threshold="1.000")
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    db_session.add(RecipeIngredient(dish_id=dish.id, ingredient_id=ingredient.id, unit=Unit.kg, quantity="0.100"))
    await db_session.commit()
    await _create_user(db_session, "ws_already_low_waiter", role=UserRole.waiter)
    await _create_user(db_session, "ws_already_low_cook", role=UserRole.cook)
    await _create_user(db_session, "ws_already_low_wm", role=UserRole.warehouse_manager)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_already_low_waiter")
        cook_token = await _login_over_http(port, "ws_already_low_cook")
        wm_token = await _login_over_http(port, "ws_already_low_wm")

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

                # Assert: 0.800 - 0.100 = 0.700, still below 1.000 — no crossing, nothing broadcast.
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(wm_ws.recv(), timeout=0.5)


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
async def test_marking_the_only_item_ready_broadcasts_order_status_changed_to_waiter_only(
    db_session,
) -> None:
    # Arrange: a single-item Order, so marking that item ready flips the Order's derived
    # status from in_preparation straight to ready (Story 5.3, FR-12/AC2), which is the case
    # that must broadcast order.status_changed.
    table = RestaurantTable(table_number=7, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="Order Status Dish",
        price="11.00",
        category_id=category.id,
        prep_time_minutes=10,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    await _create_user(db_session, "ws_order_status_waiter", role=UserRole.waiter)
    await _create_user(db_session, "ws_order_status_cook", role=UserRole.cook)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_order_status_waiter")
        cook_token = await _login_over_http(port, "ws_order_status_cook")

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
                    # Act
                    ready_response = await http_client.post(
                        f"/api/orders/{order_id}/items/{item_id}/mark-ready"
                    )
                    assert ready_response.status_code == 200

                    # Assert: the Waiter receives order.item_status_changed first (the item-level
                    # event, unconditional), then order.status_changed second (conditional on the
                    # Order's derived status having actually moved).
                    item_message = json.loads(await asyncio.wait_for(waiter_ws.recv(), timeout=2))
                    assert item_message["event"] == "order.item_status_changed"

                    order_message = json.loads(await asyncio.wait_for(waiter_ws.recv(), timeout=2))
                    assert order_message["event"] == "order.status_changed"
                    assert order_message["payload"]["id"] == order_id
                    assert order_message["payload"]["status"] == "ready"

                    # Assert: a connected Cook receives the item-level event (unchanged
                    # recipient list) but not order.status_changed, which is waiter-only.
                    cook_message = json.loads(await asyncio.wait_for(cook_ws.recv(), timeout=2))
                    assert cook_message["event"] == "order.item_status_changed"
                    with pytest.raises(asyncio.TimeoutError):
                        await asyncio.wait_for(cook_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_cancelling_one_of_several_pending_items_broadcasts_no_order_status_changed(
    db_session,
) -> None:
    # Arrange: two pending items on one Order (aggregate is in_preparation, FR-12's "anything
    # else" bucket). Cancelling one still leaves one non-cancelled pending item, so the
    # aggregate reads in_preparation both before and after — _recompute_order_status must not
    # manufacture a no-op order.status_changed broadcast (Story 5.3). cancel_item itself DOES
    # broadcast order.item_status_changed unconditionally as of Story 5.5 (this test's own name
    # and top-level claim predate that story; only the order-level no-op claim still holds).
    table = RestaurantTable(table_number=8, capacity=4, status=TableStatus.available)
    category = Category(name="Mains")
    db_session.add_all([table, category])
    await db_session.commit()
    await db_session.refresh(table)
    await db_session.refresh(category)
    dish = Dish(
        name="No Op Dish",
        price="8.00",
        category_id=category.id,
        prep_time_minutes=5,
        is_available=True,
    )
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    await _create_user(db_session, "ws_noop_waiter", role=UserRole.waiter)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_noop_waiter")

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
            http_client.cookies.set(COOKIE_NAME, waiter_token)
            open_response = await http_client.post(f"/api/orders/tables/{table.id}/open")
            assert open_response.status_code == 201
            order_id = open_response.json()["id"]
            first_add = await http_client.post(
                f"/api/orders/{order_id}/items", json={"dish_id": dish.id, "quantity": 1}
            )
            assert first_add.status_code == 201
            second_add = await http_client.post(
                f"/api/orders/{order_id}/items", json={"dish_id": dish.id, "quantity": 1}
            )
            assert second_add.status_code == 201
            item_to_cancel_id = second_add.json()["id"]

            async with await _connect(port, waiter_token) as waiter_ws:
                # Act
                cancel_response = await http_client.post(
                    f"/api/orders/{order_id}/items/{item_to_cancel_id}/cancel"
                )
                assert cancel_response.status_code == 200

                # Assert: the Waiter receives order.item_status_changed (Story 5.5, the item was
                # genuinely cancelled), then nothing further — the no-op recompute must not
                # manufacture an order.status_changed on top of it (Story 5.3).
                item_message = json.loads(await asyncio.wait_for(waiter_ws.recv(), timeout=2))
                assert item_message["event"] == "order.item_status_changed"
                assert item_message["payload"]["id"] == item_to_cancel_id
                assert item_message["payload"]["status"] == "cancelled"
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(waiter_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_marking_an_order_served_broadcasts_order_status_changed_to_waiter_only(db_session) -> None:
    # Arrange: a freshly opened Order (zero items, `pending`) — the AC1 "or zero items" branch,
    # so mark-served needs no item setup to reach an eligible state (Story 5.4).
    table = RestaurantTable(table_number=9, capacity=4, status=TableStatus.available)
    db_session.add(table)
    await db_session.commit()
    await db_session.refresh(table)
    await _create_user(db_session, "ws_serve_waiter", role=UserRole.waiter)
    await _create_user(db_session, "ws_serve_cook", role=UserRole.cook)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_serve_waiter")
        cook_token = await _login_over_http(port, "ws_serve_cook")

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
            http_client.cookies.set(COOKIE_NAME, waiter_token)
            open_response = await http_client.post(f"/api/orders/tables/{table.id}/open")
            assert open_response.status_code == 201
            order_id = open_response.json()["id"]

            async with await _connect(port, waiter_token) as waiter_ws:
                async with await _connect(port, cook_token) as cook_ws:
                    # Act
                    serve_response = await http_client.post(f"/api/orders/{order_id}/serve")
                    assert serve_response.status_code == 200

                    # Assert: the Waiter receives order.status_changed.
                    order_message = json.loads(await asyncio.wait_for(waiter_ws.recv(), timeout=2))
                    assert order_message["event"] == "order.status_changed"
                    assert order_message["payload"]["id"] == order_id
                    assert order_message["payload"]["status"] == "served"

                    # Assert: a connected Cook receives nothing — order.status_changed is
                    # waiter-only (Story 5.3's own precedent, unchanged here).
                    with pytest.raises(asyncio.TimeoutError):
                        await asyncio.wait_for(cook_ws.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_closing_an_order_broadcasts_order_status_changed_and_table_status_changed(db_session) -> None:
    # Arrange: a served Order, ready to close.
    table = RestaurantTable(table_number=10, capacity=4, status=TableStatus.available)
    db_session.add(table)
    await db_session.commit()
    await db_session.refresh(table)
    await _create_user(db_session, "ws_close_waiter", role=UserRole.waiter)

    async with _running_server() as port:
        waiter_token = await _login_over_http(port, "ws_close_waiter")

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http_client:
            http_client.cookies.set(COOKIE_NAME, waiter_token)
            open_response = await http_client.post(f"/api/orders/tables/{table.id}/open")
            assert open_response.status_code == 201
            order_id = open_response.json()["id"]
            serve_response = await http_client.post(f"/api/orders/{order_id}/serve")
            assert serve_response.status_code == 200

            async with await _connect(port, waiter_token) as waiter_ws:
                # Act
                close_response = await http_client.post(f"/api/orders/{order_id}/close")
                assert close_response.status_code == 200

                # Assert: order.status_changed first (the reused Story 5.3 helper), then
                # table.status_changed (the Table returning to available, mirroring open_table's
                # own broadcast shape).
                order_message = json.loads(await asyncio.wait_for(waiter_ws.recv(), timeout=2))
                assert order_message["event"] == "order.status_changed"
                assert order_message["payload"]["status"] == "closed"

                table_message = json.loads(await asyncio.wait_for(waiter_ws.recv(), timeout=2))
                assert table_message["event"] == "table.status_changed"
                assert table_message["payload"] == {"table_id": table.id, "status": "available"}


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
