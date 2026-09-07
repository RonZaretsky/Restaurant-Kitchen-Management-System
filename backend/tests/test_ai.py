import asyncio
from decimal import Decimal

import pytest
import pytest_asyncio
from dependency_injector import providers
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import (
    AIChatMessage,
    AIRecipeSuggestion,
    Category,
    Dish,
    Ingredient,
    Unit,
    User,
    UserRole,
)
from main import container
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


async def _login_as(client: AsyncClient, db_session: AsyncSession, role: UserRole, username: str) -> User:
    user = await _create_user(db_session, username=username, role=role)
    await _login(client, username)
    return user


class FakeLLMClient:
    """A test double for `clients.llm.LLMClient`.

    Overriding `Container.llm_client` with an instance of this class, then resetting
    `Container.ai_service`'s cached Singleton (see `fake_llm_client` fixture below), is how every
    test in this file avoids a real network call to OpenAI. Configurable per test via
    `response`/`error`/`block_event` rather than subclassing, since every test needs a slightly
    different canned behavior.
    """

    def __init__(self) -> None:
        self.response: dict | None = {
            "name": "Roasted Zucchini Flatbread",
            "ingredients": [{"name": "Zucchini", "quantity": "1.2 kg"}],
            "plating": "Sliced thin, served on a wooden board.",
        }
        self.error: Exception | None = None
        self.block_event: asyncio.Event | None = None
        self.calls: list[str] = []
        # Set the instant a call actually starts, i.e. after AIService's own
        # `_in_flight.add(actor.id)` has already run — awaited by the concurrency test instead of
        # a fixed sleep, so it never races the guard it's testing.
        self.started = asyncio.Event()
        # Chat-message configurable behavior, mirroring generate_recipe's own shape
        # exactly rather than building a second fake.
        self.chat_response: str | None = "Try adding a pinch of nutmeg, it complements the zucchini."
        self.chat_error: Exception | None = None
        self.chat_calls: list[list[dict[str, str]]] = []
        self.chat_started = asyncio.Event()
        # Suggestion-tied chat mutates the recipe: send_chat_message_with_
        # recipe_update reuses chat_calls/chat_started/block_event/chat_error, the same shape
        # send_chat_message already uses, rather than a second set of fields — only the returned
        # envelope shape differs (adds updated_recipe alongside reply).
        self.chat_updated_recipe: dict | None = None

    async def generate_recipe(self, prompt: str) -> dict:
        self.calls.append(prompt)
        is_first_call = len(self.calls) == 1
        # Signals a test waiting to know the call has genuinely started (and, since this method
        # only runs once `_in_flight` already holds the caller's id, that the guard's own state
        # is already set) before it fires a second, concurrent request — replaces a fixed
        # `asyncio.sleep` with a deterministic wait.
        if is_first_call:
            self.started.set()
        # Only the first call ever blocks on block_event — a second, concurrent call (e.g. from a
        # different Cook, who must NOT be blocked by the first Cook's in-flight generation) always
        # proceeds immediately. Two calls sharing one block_event with no way to distinguish them
        # would deadlock: nothing sets the event until a caller has already (successfully) awaited
        # the second call.
        if self.block_event is not None and is_first_call:
            await self.block_event.wait()
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response

    async def send_chat_message(self, messages: list[dict[str, str]]) -> str:
        self.chat_calls.append(messages)
        is_first_call = len(self.chat_calls) == 1
        if is_first_call:
            self.chat_started.set()
        if self.block_event is not None and is_first_call:
            await self.block_event.wait()
        if self.chat_error is not None:
            raise self.chat_error
        assert self.chat_response is not None
        return self.chat_response

    async def send_chat_message_with_recipe_update(self, messages: list[dict[str, str]]) -> dict:
        self.chat_calls.append(messages)
        is_first_call = len(self.chat_calls) == 1
        if is_first_call:
            self.chat_started.set()
        if self.block_event is not None and is_first_call:
            await self.block_event.wait()
        if self.chat_error is not None:
            raise self.chat_error
        assert self.chat_response is not None
        return {"reply": self.chat_response, "updated_recipe": self.chat_updated_recipe}


@pytest_asyncio.fixture
async def fake_llm_client():
    fake = FakeLLMClient()
    container.llm_client.override(providers.Object(fake))
    container.ai_service.reset()
    yield fake
    container.llm_client.reset_override()
    container.ai_service.reset()


async def _create_ingredient(
    db_session: AsyncSession, name: str, current_stock: str, min_stock_threshold: str
) -> Ingredient:
    ingredient = Ingredient(
        name=name, unit=Unit.kg, current_stock=current_stock, min_stock_threshold=min_stock_threshold
    )
    db_session.add(ingredient)
    await db_session.commit()
    await db_session.refresh(ingredient)
    return ingredient


@pytest.mark.asyncio
async def test_generating_a_suggestion_persists_prompt_snapshot_and_recipe(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange
    await _create_ingredient(db_session, "Zucchini", "5.000", "1.000")
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.post("/api/smart-chef/suggestions", json={"direction": "something for dessert"})

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["generated_recipe"] == fake_llm_client.response
    assert "something for dessert" in body["prompt_used"]
    assert body["ingredients_snapshot"] == [{"name": "Zucchini", "unit": "kg", "current_stock": "5.000"}]

    db_session.expire_all()
    saved = await db_session.get(AIRecipeSuggestion, body["id"])
    cook = (await db_session.execute(select(User).where(User.username == "amir"))).scalar_one()
    assert saved.requested_by == cook.id


@pytest.mark.asyncio
async def test_a_direction_never_overrides_the_stock_constraint_in_the_prompt(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange
    await _create_ingredient(db_session, "Flour", "10.000", "1.000")
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.post("/api/smart-chef/suggestions", json={"direction": "want it spicy"})

    # Assert: the direction is folded into the prompt alongside an explicit
    # never-override-stock instruction, not a separate persisted field.
    assert response.status_code == 201
    prompt = fake_llm_client.calls[0]
    assert "want it spicy" in prompt
    assert "never include an ingredient that is not listed above" in prompt
    assert "direction" not in response.json()


@pytest.mark.asyncio
async def test_a_malformed_llm_response_is_rejected_and_persists_nothing(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: syntactically valid JSON, but missing the expected keys.
    await _create_ingredient(db_session, "Basil", "2.000", "1.000")
    await _login_as(client, db_session, UserRole.cook, "amir")
    fake_llm_client.response = {"unexpected": "shape"}

    # Act
    response = await client.post("/api/smart-chef/suggestions", json={})

    # Assert
    assert response.status_code == 502
    assert response.json()["detail"] == "Couldn't generate a suggestion right now"
    result = await db_session.execute(select(AIRecipeSuggestion))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_generate_suggestion_role_coverage(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange/Act/Assert: waiter, warehouse_manager, admin are all 403 (Cook-only, no admin
    # fallback); unauthenticated is 401.
    await _login_as(client, db_session, UserRole.waiter, "maya")
    assert (await client.post("/api/smart-chef/suggestions", json={})).status_code == 403

    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    assert (await client.post("/api/smart-chef/suggestions", json={})).status_code == 403

    await _login_as(client, db_session, UserRole.admin, "david")
    assert (await client.post("/api/smart-chef/suggestions", json={})).status_code == 403

    client.cookies.clear()
    assert (await client.post("/api/smart-chef/suggestions", json={})).status_code == 401


async def _create_suggestion(db_session: AsyncSession, requested_by: int, dismissed: bool = False) -> AIRecipeSuggestion:
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


@pytest.mark.asyncio
async def test_list_suggestions_reports_the_real_dish_id_once_confirmed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: the null cases are covered elsewhere; this one covers the headline behavior,
    # confirmed_dish_id reflecting a real Dish.
    admin = await _login_as(client, db_session, UserRole.admin, "david")
    suggestion = await _create_suggestion(db_session, requested_by=admin.id)
    category_response = await client.post("/api/menu/categories", json={"name": "Pizza"})
    assert category_response.status_code == 201
    dish_response = await client.post(
        "/api/menu/dishes",
        json={
            "name": "Flatbread",
            "price": "12.50",
            "category_id": category_response.json()["id"],
            "source_suggestion_id": suggestion.id,
        },
    )
    assert dish_response.status_code == 201

    # Act
    response = await client.get("/api/smart-chef/suggestions")

    # Assert
    body = {item["id"]: item for item in response.json()}
    assert body[suggestion.id]["confirmed_dish_id"] == dish_response.json()["id"]


@pytest.mark.asyncio
async def test_dismissing_a_suggestion_sets_dismissed_true(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    admin = await _login_as(client, db_session, UserRole.admin, "david")
    suggestion = await _create_suggestion(db_session, requested_by=admin.id)
    suggestion_id = suggestion.id

    # Act
    response = await client.post(f"/api/smart-chef/suggestions/{suggestion_id}/dismiss")

    # Assert
    assert response.status_code == 200
    assert response.json()["dismissed"] is True
    db_session.expire_all()
    saved = await db_session.get(AIRecipeSuggestion, suggestion_id)
    assert saved.dismissed is True


# --- Smart Chef chat: consulting on a Dish, and revising a suggestion ------------------------


async def _create_dish(db_session: AsyncSession, name: str = "Flatbread") -> Dish:
    # Created directly against the DB, not through POST /api/menu/dishes (admin-only) — these
    # tests act as a Cook throughout, matching _create_ingredient's own direct-insert precedent
    # rather than juggling a login switch just to seed a Dish fixture.
    category = Category(name=f"{name} Category")
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    dish = Dish(name=name, price=Decimal("12.50"), category_id=category.id, is_available=False)
    db_session.add(dish)
    await db_session.commit()
    await db_session.refresh(dish)
    return dish


@pytest.mark.asyncio
async def test_creating_a_chat_session_tied_to_a_dish_and_sending_a_message_persists_two_messages(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "amir")
    dish = await _create_dish(db_session, "Flatbread")

    # Act
    session_response = await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})
    assert session_response.status_code == 201
    session_body = session_response.json()
    assert session_body["title"] == f"Chat about {dish.name}"
    assert session_body["dish_id"] == dish.id
    assert session_body["suggestion_id"] is None

    send_response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_body['id']}/messages", json={"content": "How do I improve this?"}
    )

    # Assert
    assert send_response.status_code == 201
    messages = send_response.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "How do I improve this?"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == fake_llm_client.chat_response

    list_response = await client.get(f"/api/smart-chef/chat-sessions/{session_body['id']}/messages")
    assert list_response.status_code == 200
    assert [m["role"] for m in list_response.json()] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_creating_a_chat_session_tied_to_a_suggestion_and_sending_a_message_persists_two_messages(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange
    cook = await _login_as(client, db_session, UserRole.cook, "amir")
    suggestion = await _create_suggestion(db_session, requested_by=cook.id)

    # Act
    session_response = await client.post(
        "/api/smart-chef/chat-sessions", json={"suggestion_id": suggestion.id}
    )
    assert session_response.status_code == 201
    session_body = session_response.json()
    assert session_body["title"] == f"Chat about {suggestion.generated_recipe['name']}"
    assert session_body["suggestion_id"] == suggestion.id
    assert session_body["dish_id"] is None

    send_response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_body['id']}/messages", json={"content": "Can it be spicier?"}
    )

    # Assert
    assert send_response.status_code == 201
    messages = send_response.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_creating_a_chat_session_with_neither_target_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.post("/api/smart-chef/chat-sessions", json={})

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_suggestion_chat_revision_request_updates_the_generated_recipe(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: the Cook asks for a change, and the model returns an updated_recipe.
    # suggestion_id is captured as a plain int up front (not suggestion.id read later), matching
    # this file's own established pattern: accessing an attribute on an ORM object after
    # db_session.expire_all() triggers a synchronous lazy-load an AsyncSession cannot perform
    # outside an explicit await.
    cook = await _login_as(client, db_session, UserRole.cook, "amir")
    suggestion = await _create_suggestion(db_session, requested_by=cook.id)
    suggestion_id = suggestion.id
    session_id = (
        await client.post("/api/smart-chef/chat-sessions", json={"suggestion_id": suggestion_id})
    ).json()["id"]
    updated_recipe = {
        "name": "Vegan Roasted Zucchini Flatbread",
        "ingredients": [{"name": "Zucchini", "quantity": "1.2 kg"}],
        "plating": "Sliced thin, served on a wooden board, no cheese.",
    }
    fake_llm_client.chat_updated_recipe = updated_recipe

    # Act
    response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "Make it vegan"}
    )

    # Assert: the response's own two messages persist as usual...
    assert response.status_code == 201
    messages = response.json()
    assert messages[1]["content"] == fake_llm_client.chat_response

    # ...and the Suggestion's generated_recipe is updated in the same transaction.
    db_session.expire_all()
    saved = await db_session.get(AIRecipeSuggestion, suggestion_id)
    assert saved.generated_recipe == updated_recipe

    # The Admin-facing list also reflects the update once refetched.
    list_response = await client.get("/api/smart-chef/suggestions")
    body = {item["id"]: item for item in list_response.json()}
    assert body[suggestion_id]["generated_recipe"] == updated_recipe


@pytest.mark.asyncio
async def test_a_malformed_updated_recipe_shape_is_rejected_and_persists_no_messages(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: syntactically valid JSON, but updated_recipe is missing the expected keys.
    cook = await _login_as(client, db_session, UserRole.cook, "amir")
    suggestion = await _create_suggestion(db_session, requested_by=cook.id)
    suggestion_id = suggestion.id
    original_recipe = suggestion.generated_recipe
    session_id = (
        await client.post("/api/smart-chef/chat-sessions", json={"suggestion_id": suggestion_id})
    ).json()["id"]
    fake_llm_client.chat_updated_recipe = {"unexpected": "shape"}

    # Act
    response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "Make it vegan"}
    )

    # Assert
    assert response.status_code == 502
    assert response.json()["detail"] == "Couldn't get a response right now"
    result = await db_session.execute(select(AIChatMessage).where(AIChatMessage.session_id == session_id))
    assert result.scalars().all() == []
    db_session.expire_all()
    saved = await db_session.get(AIRecipeSuggestion, suggestion_id)
    assert saved.generated_recipe == original_recipe


@pytest.mark.asyncio
async def test_a_dish_tied_session_never_calls_the_recipe_update_method(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: a Dish-tied session stays on the free-text contract even when the fake would
    # otherwise report an updated_recipe, proving the branch, not just the response shape.
    await _login_as(client, db_session, UserRole.cook, "amir")
    dish = await _create_dish(db_session, "Flatbread")
    session_id = (await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})).json()["id"]
    fake_llm_client.chat_updated_recipe = {
        "name": "Should never apply",
        "ingredients": [],
        "plating": "n/a",
    }

    # Act
    response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "Any tips?"}
    )

    # Assert: succeeds via the plain free-text reply, never the JSON envelope method.
    assert response.status_code == 201
    assert response.json()[1]["content"] == fake_llm_client.chat_response

