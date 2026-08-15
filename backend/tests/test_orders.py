import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import Order, RestaurantTable, TableStatus, User, UserRole
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
