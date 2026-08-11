import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import Ingredient, RecipeIngredient, Unit, User, UserRole
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


async def _create_category(client: AsyncClient, name: str) -> dict:
    response = await client.post("/api/menu/categories", json={"name": name})
    assert response.status_code == 201
    return response.json()


async def _create_dish(client: AsyncClient, category_id: int, name: str = "Margherita") -> dict:
    response = await client.post(
        "/api/menu/dishes",
        json={"name": name, "price": "12.50", "category_id": category_id, "prep_time_minutes": 15},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_admin_can_create_a_category(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.post("/api/menu/categories", json={"name": "Starters"})

    # Assert
    assert response.status_code == 201
    assert response.json()["name"] == "Starters"


@pytest.mark.asyncio
async def test_duplicate_category_name_same_case_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    await _create_category(client, "Mains")

    # Act
    response = await client.post("/api/menu/categories", json={"name": "Mains"})

    # Assert
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_warehouse_manager_cannot_create_a_category(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _create_user(db_session, "noa", UserRole.warehouse_manager)
    await _login(client, "noa")

    # Act
    response = await client.post("/api/menu/categories", json={"name": "Desserts"})

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cook_cannot_create_a_category(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _create_user(db_session, "cook1", UserRole.cook)
    await _login(client, "cook1")

    # Act
    response = await client.post("/api/menu/categories", json={"name": "Desserts"})

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_is_rejected(client: AsyncClient) -> None:
    # Act
    response = await client.post("/api/menu/categories", json={"name": "Desserts"})

    # Assert
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_create_a_dish_and_it_starts_unavailable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")

    # Act
    response = await client.post(
        "/api/menu/dishes",
        json={
            "name": "Margherita",
            "description": "Tomato, mozzarella, basil",
            "price": "12.50",
            "category_id": category["id"],
            "prep_time_minutes": 15,
        },
    )

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Margherita"
    assert body["is_available"] is False


@pytest.mark.asyncio
async def test_creating_a_dish_with_a_nonexistent_category_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.post(
        "/api/menu/dishes",
        json={"name": "Margherita", "price": "12.50", "category_id": 999999},
    )

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_marking_a_dish_available_with_no_recipe_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])

    # Act
    response = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"is_available": True})

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot mark available, recipe has no ingredients"


@pytest.mark.asyncio
async def test_updating_a_dishes_price_and_name_succeeds(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])

    # Act
    response = await client.patch(
        f"/api/menu/dishes/{dish['id']}", json={"name": "Margherita Deluxe", "price": "15.00"}
    )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Margherita Deluxe"
    assert body["price"] == "15.00"


@pytest.mark.asyncio
async def test_update_with_no_fields_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])

    # Act
    response = await client.patch(f"/api/menu/dishes/{dish['id']}", json={})

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_on_a_nonexistent_dish_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act
    response = await client.patch("/api/menu/dishes/999999", json={"name": "Ghost Dish"})

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_negative_price_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")

    # Act
    response = await client.post(
        "/api/menu/dishes",
        json={"name": "Margherita", "price": "-5.00", "category_id": category["id"]},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_price_exceeding_the_column_precision_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")

    # Act: the dishes.price column is Numeric(8, 2), so this value has more total
    # digits than the column allows. Without a matching Pydantic bound, this would
    # reach the database and raise an unhandled asyncpg.NumericValueOutOfRangeError
    # (a 500) instead of a clean 422.
    response = await client.post(
        "/api/menu/dishes",
        json={"name": "Margherita", "price": "1234567.89", "category_id": category["id"]},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_negative_prep_time_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")

    # Act
    response = await client.post(
        "/api/menu/dishes",
        json={"name": "Margherita", "price": "12.50", "category_id": category["id"], "prep_time_minutes": -5},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_price_with_too_many_decimal_places_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")

    # Act: within the 8-total-digit budget, but 3 decimal places exceeds decimal_places=2.
    response = await client.post(
        "/api/menu/dishes",
        json={"name": "Margherita", "price": "12.555", "category_id": category["id"]},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_category_id_exceeding_int4_range_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)

    # Act: without an upper bound, this reaches the database and raises an unhandled
    # asyncpg.DataError ("value out of int32 range") instead of a clean 422.
    response = await client.post(
        "/api/menu/dishes",
        json={"name": "Margherita", "price": "12.50", "category_id": 99999999999999},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_prep_time_exceeding_int4_range_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")

    # Act
    response = await client.post(
        "/api/menu/dishes",
        json={
            "name": "Margherita",
            "price": "12.50",
            "category_id": category["id"],
            "prep_time_minutes": 99999999999999,
        },
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_marking_a_dish_available_succeeds_once_it_has_a_recipe_ingredient(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])

    ingredient = Ingredient(name="Flour", unit=Unit.kg, current_stock=10, min_stock_threshold=1)
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    db_session.add(
        RecipeIngredient(dish_id=dish["id"], ingredient_id=ingredient.id, unit=Unit.kg, quantity=1)
    )
    await db_session.commit()

    # Act
    response = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"is_available": True})

    # Assert
    assert response.status_code == 200
    assert response.json()["is_available"] is True


@pytest.mark.asyncio
async def test_updating_to_a_nonexistent_category_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])

    # Act
    response = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"category_id": 999999})

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_dish_request_ignores_a_submitted_is_available_field(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")

    # Act: is_available is not a field CreateDishRequest declares; Pydantic silently
    # drops it, and the Dish must still start unavailable regardless (AC2).
    response = await client.post(
        "/api/menu/dishes",
        json={"name": "Margherita", "price": "12.50", "category_id": category["id"], "is_available": True},
    )

    # Assert
    assert response.status_code == 201
    assert response.json()["is_available"] is False


@pytest.mark.asyncio
async def test_category_names_differing_only_by_case_are_both_accepted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    await _create_category(client, "Mains")

    # Act: category duplicate rejection is deliberately case-sensitive only, unlike
    # Ingredient names or usernames.
    response = await client.post("/api/menu/categories", json={"name": "mains"})

    # Assert
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_warehouse_manager_cannot_create_a_dish(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session, "admin_setup")
    category = await _create_category(client, "Pizza")
    await _create_user(db_session, "noa", UserRole.warehouse_manager)
    await _login(client, "noa")

    # Act
    response = await client.post(
        "/api/menu/dishes", json={"name": "Margherita", "price": "12.50", "category_id": category["id"]}
    )

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cook_cannot_update_a_dish(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session, "admin_setup")
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    await _create_user(db_session, "cook1", UserRole.cook)
    await _login(client, "cook1")

    # Act
    response = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"name": "Renamed"})

    # Assert
    assert response.status_code == 403
