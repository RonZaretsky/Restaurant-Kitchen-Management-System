import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import RestaurantTable, TableStatus, User, UserRole
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


async def _create_table(client: AsyncClient, table_number: int, capacity: int = 4) -> dict:
    response = await client.post(
        "/api/tables/", json={"table_number": table_number, "capacity": capacity}
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_admin_can_create_a_table_and_it_starts_available(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.post("/api/tables/", json={"table_number": 1, "capacity": 4})

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["table_number"] == 1
    assert body["capacity"] == 4
    assert body["status"] == "available"


@pytest.mark.asyncio
async def test_duplicate_table_number_on_create_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    await _create_table(client, 5)

    # Act
    response = await client.post("/api/tables/", json={"table_number": 5, "capacity": 2})

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, table number already exists"


@pytest.mark.asyncio
async def test_admin_can_edit_an_available_table(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    table = await _create_table(client, 1)

    # Act
    response = await client.patch(f"/api/tables/{table['id']}", json={"table_number": 2, "capacity": 6})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["table_number"] == 2
    assert body["capacity"] == 6


@pytest.mark.asyncio
async def test_editing_an_occupied_table_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    table = await _create_table(client, 1)
    db_table = await db_session.get(RestaurantTable, table["id"])
    db_table.status = TableStatus.occupied
    await db_session.commit()

    # Act
    response = await client.patch(f"/api/tables/{table['id']}", json={"capacity": 8})

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, table in use"


@pytest.mark.asyncio
async def test_editing_a_reserved_table_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    table = await _create_table(client, 1)
    db_table = await db_session.get(RestaurantTable, table["id"])
    db_table.status = TableStatus.reserved
    await db_session.commit()

    # Act
    response = await client.patch(f"/api/tables/{table['id']}", json={"capacity": 8})

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, table in use"


@pytest.mark.asyncio
async def test_renaming_a_table_to_another_tables_number_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    await _create_table(client, 1)
    table_2 = await _create_table(client, 2)

    # Act: table_2 is itself available, the number collision is the actual conflict.
    response = await client.patch(f"/api/tables/{table_2['id']}", json={"table_number": 1})

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, table number already exists"


@pytest.mark.asyncio
async def test_race_between_form_load_and_save_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: this is AC6, the story's core rule. The Admin "loads the form"
    # (the table is available at that point); a Waiter "seats the table" by the
    # time the save commits, simulated by committing a status change via the
    # test's own db_session (a separate connection from the app's) immediately
    # before the PATCH, so the guarded UPDATE reads live, already-changed state.
    await _login_as_admin(client, db_session)
    table = await _create_table(client, 1)
    db_table = await db_session.get(RestaurantTable, table["id"])
    db_table.status = TableStatus.occupied
    await db_session.commit()

    # Act
    response = await client.patch(f"/api/tables/{table['id']}", json={"capacity": 8})

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, table in use"


@pytest.mark.asyncio
async def test_editing_with_no_fields_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    table = await _create_table(client, 1)

    # Act
    response = await client.patch(f"/api/tables/{table['id']}", json={})

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_editing_a_nonexistent_table_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.patch("/api/tables/999999", json={"capacity": 4})

    # Assert
    assert response.status_code == 404
    assert response.json()["detail"] == "Table not found"


@pytest.mark.asyncio
async def test_negative_capacity_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.post("/api/tables/", json={"table_number": 1, "capacity": -1})

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_zero_table_number_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.post("/api/tables/", json={"table_number": 0, "capacity": 4})

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_table_number_exceeding_int4_range_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act: without an upper bound, this reaches the database and raises an unhandled
    # asyncpg.DataError ("value out of int32 range") instead of a clean 422.
    response = await client.post("/api/tables/", json={"table_number": 99999999999999, "capacity": 4})

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_table_id_path_param_exceeding_int4_range_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.patch("/api/tables/99999999999999", json={"capacity": 4})

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_warehouse_manager_cannot_create_a_table(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _create_user(db_session, "noa", UserRole.warehouse_manager)
    await _login(client, "noa")

    # Act
    response = await client.post("/api/tables/", json={"table_number": 1, "capacity": 4})

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_waiter_cannot_edit_a_table(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session, "admin_setup")
    table = await _create_table(client, 1)
    await _create_user(db_session, "waiter1", UserRole.waiter)
    await _login(client, "waiter1")

    # Act
    response = await client.patch(f"/api/tables/{table['id']}", json={"capacity": 8})

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cook_cannot_list_tables(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _create_user(db_session, "cook1", UserRole.cook)
    await _login(client, "cook1")

    # Act
    response = await client.get("/api/tables/")

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_is_rejected(client: AsyncClient) -> None:
    # Act
    response = await client.post("/api/tables/", json={"table_number": 1, "capacity": 4})

    # Assert
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_list_tables(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    table = await _create_table(client, 1)

    # Act
    response = await client.get("/api/tables/")

    # Assert
    assert response.status_code == 200
    assert any(t["id"] == table["id"] for t in response.json())
