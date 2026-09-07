import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import AIRecipeSuggestion, Ingredient, RecipeIngredient, Unit, User, UserRole
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


async def _create_ingredient(db_session: AsyncSession, name: str = "Flour") -> Ingredient:
    ingredient = Ingredient(name=name, unit=Unit.kg, current_stock=10, min_stock_threshold=1)
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    return ingredient


async def _create_suggestion(
    db_session: AsyncSession, requested_by: int, dismissed: bool = False
) -> AIRecipeSuggestion:
    suggestion = AIRecipeSuggestion(
        requested_by=requested_by,
        prompt_used="...",
        generated_recipe={
            "name": "Roasted Zucchini Flatbread",
            "ingredients": [{"name": "Zucchini", "quantity": "1.2 kg"}],
            "plating": "Sliced thin, served on a wooden board.",
        },
        ingredients_snapshot=[{"name": "Zucchini", "unit": "kg", "current_stock": "5.000"}],
        dismissed=dismissed,
    )
    db_session.add(suggestion)
    await db_session.commit()
    await db_session.refresh(suggestion)
    return suggestion


async def _add_recipe_ingredient(
    client: AsyncClient, dish_id: int, ingredient_id: int, quantity: str = "0.500", unit: str = "kg"
) -> dict:
    response = await client.post(
        f"/api/menu/dishes/{dish_id}/recipe-ingredients",
        json={"ingredient_id": ingredient_id, "quantity": quantity, "unit": unit},
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
async def test_creating_a_dish_with_a_source_suggestion_id_confirms_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: Story 6.2 - Confirm into Dish. "Confirmed" is derived, not stored, so the
    # assertion is that a Dish now cites the suggestion, not a flag on the suggestion itself.
    admin = await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    suggestion = await _create_suggestion(db_session, requested_by=admin.id)

    # Act
    response = await client.post(
        "/api/menu/dishes",
        json={
            "name": "Roasted Zucchini Flatbread",
            "price": "12.50",
            "category_id": category["id"],
            "source_suggestion_id": suggestion.id,
        },
    )

    # Assert
    assert response.status_code == 201
    assert response.json()["source_suggestion_id"] == suggestion.id


@pytest.mark.asyncio
async def test_creating_a_second_dish_from_an_already_confirmed_suggestion_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: FR-19 - there is only one Dish-creation path, so this confirms the
    # already-confirmed check rather than a bypass of it.
    admin = await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    suggestion = await _create_suggestion(db_session, requested_by=admin.id)
    first = await client.post(
        "/api/menu/dishes",
        json={
            "name": "Flatbread",
            "price": "12.50",
            "category_id": category["id"],
            "source_suggestion_id": suggestion.id,
        },
    )
    assert first.status_code == 201

    # Act
    second = await client.post(
        "/api/menu/dishes",
        json={
            "name": "Flatbread Redux",
            "price": "9.00",
            "category_id": category["id"],
            "source_suggestion_id": suggestion.id,
        },
    )

    # Assert
    assert second.status_code == 409


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


@pytest.mark.asyncio
async def test_admin_can_list_categories_and_dishes(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])

    # Act
    categories_response = await client.get("/api/menu/categories")
    dishes_response = await client.get("/api/menu/dishes")

    # Assert
    assert categories_response.status_code == 200
    assert any(c["id"] == category["id"] for c in categories_response.json())
    assert dishes_response.status_code == 200
    assert any(d["id"] == dish["id"] for d in dishes_response.json())


@pytest.mark.asyncio
async def test_admin_can_add_a_recipe_ingredient_and_read_it_back(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    ingredient = await _create_ingredient(db_session)

    # Act
    add_response = await client.post(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients",
        json={"ingredient_id": ingredient.id, "quantity": "0.300", "unit": "kg"},
    )
    read_response = await client.get(f"/api/menu/dishes/{dish['id']}/recipe-ingredients")

    # Assert (AC1, AC3: the read-back reflects what was just saved)
    assert add_response.status_code == 201
    body = add_response.json()
    assert body["dish_id"] == dish["id"]
    assert body["ingredient_id"] == ingredient.id
    assert body["quantity"] == "0.300"
    assert read_response.status_code == 200
    assert len(read_response.json()) == 1


@pytest.mark.asyncio
async def test_adding_a_recipe_ingredient_for_a_deactivated_ingredient_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: this batch's #4 guard — a *new* Recipe Ingredient line is blocked against a
    # deactivated Ingredient.
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    ingredient = await _create_ingredient(db_session)
    deactivate_response = await client.post(f"/api/inventory/ingredients/{ingredient.id}/deactivate")
    assert deactivate_response.status_code == 200

    # Act
    response = await client.post(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients",
        json={"ingredient_id": ingredient.id, "quantity": "0.300", "unit": "kg"},
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "Rejected, ingredient is deactivated"
    read_response = await client.get(f"/api/menu/dishes/{dish['id']}/recipe-ingredients")
    assert read_response.json() == []


@pytest.mark.asyncio
async def test_adding_a_duplicate_recipe_ingredient_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    ingredient = await _create_ingredient(db_session)
    await _add_recipe_ingredient(client, dish["id"], ingredient.id)

    # Act
    response = await client.post(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients",
        json={"ingredient_id": ingredient.id, "quantity": "1.000", "unit": "kg"},
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "That ingredient is already on this dish's recipe"


@pytest.mark.asyncio
async def test_updating_a_recipe_ingredients_quantity_succeeds_and_persists(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    ingredient = await _create_ingredient(db_session)
    await _add_recipe_ingredient(client, dish["id"], ingredient.id, quantity="0.300")

    # Act
    update_response = await client.patch(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients/{ingredient.id}", json={"quantity": "0.750"}
    )
    read_response = await client.get(f"/api/menu/dishes/{dish['id']}/recipe-ingredients")

    # Assert (AC3: the read-back reflects the new value, not the old one)
    assert update_response.status_code == 200
    assert update_response.json()["quantity"] == "0.750"
    assert read_response.json()[0]["quantity"] == "0.750"


@pytest.mark.asyncio
async def test_cannot_remove_the_last_recipe_ingredient_while_the_dish_is_available(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: this is AC2, this story's core rule.
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    ingredient = await _create_ingredient(db_session)
    await _add_recipe_ingredient(client, dish["id"], ingredient.id)
    mark_available = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"is_available": True})
    assert mark_available.status_code == 200

    # Act
    delete_while_available = await client.delete(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients/{ingredient.id}"
    )

    # Assert
    assert delete_while_available.status_code == 409
    assert (
        delete_while_available.json()["detail"]
        == "Cannot remove the last recipe ingredient while the dish is available"
    )

    # Act again: marking the dish unavailable first lets the same delete succeed.
    mark_unavailable = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"is_available": False})
    delete_after_unavailable = await client.delete(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients/{ingredient.id}"
    )

    # Assert
    assert mark_unavailable.status_code == 200
    assert delete_after_unavailable.status_code == 204


@pytest.mark.asyncio
async def test_deleting_one_of_two_lines_on_an_available_dish_succeeds(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: the last-line guard only fires at count 1, not on every delete
    # while available.
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    flour = await _create_ingredient(db_session, "Flour")
    cheese = await _create_ingredient(db_session, "Cheese")
    await _add_recipe_ingredient(client, dish["id"], flour.id)
    await _add_recipe_ingredient(client, dish["id"], cheese.id)
    mark_available = await client.patch(f"/api/menu/dishes/{dish['id']}", json={"is_available": True})
    assert mark_available.status_code == 200

    # Act
    response = await client.delete(f"/api/menu/dishes/{dish['id']}/recipe-ingredients/{flour.id}")

    # Assert
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_negative_recipe_ingredient_quantity_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    ingredient = await _create_ingredient(db_session)

    # Act
    response = await client.post(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients",
        json={"ingredient_id": ingredient.id, "quantity": "-1.000", "unit": "kg"},
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_warehouse_manager_cannot_add_a_recipe_ingredient(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session, "admin_setup")
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    ingredient = await _create_ingredient(db_session)
    await _create_user(db_session, "noa", UserRole.warehouse_manager)
    await _login(client, "noa")

    # Act
    response = await client.post(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients",
        json={"ingredient_id": ingredient.id, "quantity": "1.000", "unit": "kg"},
    )

    # Assert
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_adding_a_line_whose_unit_differs_from_the_ingredients_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: Flour is stocked in kg. Nothing in this system converts between
    # units, so a liter line against a kg ingredient would silently deduct the
    # wrong amount in Epic 5.
    await _login_as_admin(client, db_session)
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    ingredient = await _create_ingredient(db_session)

    # Act
    response = await client.post(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients",
        json={"ingredient_id": ingredient.id, "quantity": "0.500", "unit": "liter"},
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == "The line's unit must match the ingredient's own unit"


@pytest.mark.asyncio
async def test_cook_can_list_categories_and_read_a_recipe_but_not_edit_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as_admin(client, db_session, "admin_setup")
    category = await _create_category(client, "Pizza")
    dish = await _create_dish(client, category["id"])
    ingredient = await _create_ingredient(db_session, "Flour")
    created_line = await _add_recipe_ingredient(client, dish["id"], ingredient.id, quantity="0.300")
    await _create_user(db_session, "cook1", UserRole.cook)
    await _login(client, "cook1")

    # Act: Story 2.5 (FR-25) permits a Cook to read the catalog and a Dish's recipe,
    # but never to write to either.
    categories_response = await client.get("/api/menu/categories")
    recipe_response = await client.get(f"/api/menu/dishes/{dish['id']}/recipe-ingredients")
    patch_response = await client.patch(
        f"/api/menu/dishes/{dish['id']}/recipe-ingredients/{ingredient.id}", json={"quantity": "1.000"}
    )

    # Assert
    assert categories_response.status_code == 200
    assert recipe_response.status_code == 200
    # The Cook sees exactly the line the Admin created, not a stripped-down copy.
    assert recipe_response.json() == [created_line]
    assert patch_response.status_code == 403

