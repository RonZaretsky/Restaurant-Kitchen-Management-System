import asyncio
from decimal import Decimal

import pytest
import pytest_asyncio
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clients.llm import LLMClient
from data_models import (
    AIChatMessage,
    AIChatSession,
    AIRecipeSuggestion,
    Category,
    Dish,
    Ingredient,
    Unit,
    User,
    UserRole,
)
from main import app, container
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
    """A test double for `clients.llm.LLMClient` (Story 6.1's first mocking need in this suite).

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
        # a fixed sleep, so it never races the guard it's testing (review finding).
        self.started = asyncio.Event()
        # Story 6.3: chat-message configurable behavior, mirroring generate_recipe's own shape
        # exactly rather than building a second fake.
        self.chat_response: str | None = "Try adding a pinch of nutmeg, it complements the zucchini."
        self.chat_error: Exception | None = None
        self.chat_calls: list[list[dict[str, str]]] = []
        self.chat_started = asyncio.Event()
        # This batch's #7 (Suggestion-tied chat mutates the recipe): send_chat_message_with_
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
        # `asyncio.sleep` with a deterministic wait (review finding).
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
async def test_a_second_concurrent_request_from_the_same_cook_is_rejected(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: the first call blocks on an event this test controls, and the fake client signals
    # `started` only once it's genuinely mid-call (i.e. after AIService's own in-flight guard is
    # already set) — awaited deterministically below rather than a fixed sleep (review finding).
    await _create_ingredient(db_session, "Basil", "2.000", "1.000")
    await _login_as(client, db_session, UserRole.cook, "amir")
    fake_llm_client.block_event = asyncio.Event()

    # Act
    first_task = asyncio.create_task(client.post("/api/smart-chef/suggestions", json={}))
    await asyncio.wait_for(fake_llm_client.started.wait(), timeout=2)
    second_response = await client.post("/api/smart-chef/suggestions", json={})
    fake_llm_client.block_event.set()
    first_response = await first_task

    # Assert
    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Rejected, a suggestion is already generating for this Cook"


@pytest.mark.asyncio
async def test_a_different_cook_can_generate_concurrently(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: the in-flight guard is keyed by actor.id, so a second, DIFFERENT Cook must not be
    # blocked by the first Cook's own in-flight generation (every existing concurrency test used
    # only one Cook, so this was previously unverified).
    await _create_ingredient(db_session, "Basil", "2.000", "1.000")
    await _login_as(client, db_session, UserRole.cook, "amir")
    fake_llm_client.block_event = asyncio.Event()

    # Act
    first_task = asyncio.create_task(client.post("/api/smart-chef/suggestions", json={}))
    await asyncio.wait_for(fake_llm_client.started.wait(), timeout=2)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as second_client:
        await _login_as(second_client, db_session, UserRole.cook, "noa")
        second_response = await second_client.post("/api/smart-chef/suggestions", json={})

    fake_llm_client.block_event.set()
    first_response = await first_task

    # Assert
    assert first_response.status_code == 201
    assert second_response.status_code == 201


@pytest.mark.asyncio
async def test_no_ingredients_in_stock_is_rejected(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: no Ingredients at all — nothing to build a recipe from.
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.post("/api/smart-chef/suggestions", json={})

    # Assert: rejected before ever calling the LLM client.
    assert response.status_code == 502
    assert fake_llm_client.calls == []


@pytest.mark.asyncio
async def test_out_of_stock_ingredients_are_excluded_from_the_snapshot(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: one in-stock Ingredient, one at zero (AC1's "currently-available" wording).
    await _create_ingredient(db_session, "Basil", "2.000", "1.000")
    await _create_ingredient(db_session, "Saffron", "0.000", "0.100")
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.post("/api/smart-chef/suggestions", json={})

    # Assert
    assert response.status_code == 201
    snapshot_names = {item["name"] for item in response.json()["ingredients_snapshot"]}
    assert snapshot_names == {"Basil"}


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
async def test_a_failed_generation_persists_no_suggestion_and_returns_502(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange
    await _create_ingredient(db_session, "Tomato", "3.000", "1.000")
    await _login_as(client, db_session, UserRole.cook, "amir")
    fake_llm_client.error = RuntimeError("simulated OpenAI failure")

    # Act
    response = await client.post("/api/smart-chef/suggestions", json={})

    # Assert
    assert response.status_code == 502
    assert response.json()["detail"] == "Couldn't generate a suggestion right now"

    result = await db_session.execute(select(AIRecipeSuggestion))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_a_cook_can_generate_again_after_a_failed_attempt(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: the in-flight guard must clear even on failure (the finally block), not just
    # on success.
    await _create_ingredient(db_session, "Onion", "3.000", "1.000")
    await _login_as(client, db_session, UserRole.cook, "amir")
    fake_llm_client.error = RuntimeError("simulated OpenAI failure")
    first = await client.post("/api/smart-chef/suggestions", json={})
    assert first.status_code == 502

    # Act
    fake_llm_client.error = None
    second = await client.post("/api/smart-chef/suggestions", json={})

    # Assert
    assert second.status_code == 201


@pytest.mark.asyncio
async def test_get_suggestions_returns_empty_list_not_404(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/smart-chef/suggestions")

    # Assert
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_admin_can_also_list_suggestions(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.admin, "david")

    # Act
    response = await client.get("/api/smart-chef/suggestions")

    # Assert
    assert response.status_code == 200


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


@pytest.mark.asyncio
async def test_list_suggestions_role_coverage(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange/Act/Assert: waiter and warehouse_manager are 403; unauthenticated is 401.
    await _login_as(client, db_session, UserRole.waiter, "maya")
    assert (await client.get("/api/smart-chef/suggestions")).status_code == 403

    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    assert (await client.get("/api/smart-chef/suggestions")).status_code == 403

    client.cookies.clear()
    assert (await client.get("/api/smart-chef/suggestions")).status_code == 401


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
async def test_list_suggestions_includes_dismissed_and_confirmed_dish_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: Story 6.2 - list_suggestions's outerjoin must surface both new fields.
    admin = await _login_as(client, db_session, UserRole.admin, "david")
    awaiting = await _create_suggestion(db_session, requested_by=admin.id)
    dismissed = await _create_suggestion(db_session, requested_by=admin.id, dismissed=True)

    # Act
    response = await client.get("/api/smart-chef/suggestions")

    # Assert
    body = {item["id"]: item for item in response.json()}
    assert body[awaiting.id]["dismissed"] is False
    assert body[awaiting.id]["confirmed_dish_id"] is None
    assert body[dismissed.id]["dismissed"] is True


@pytest.mark.asyncio
async def test_list_suggestions_reports_the_real_dish_id_once_confirmed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: code review finding - only the null cases were previously covered, leaving the
    # headline "confirmed_dish_id reflects a real Dish" behavior unverified.
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
async def test_two_concurrent_confirms_of_the_same_suggestion_only_one_succeeds(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: code review finding - the sequential-only version of this test could not have
    # caught the missing uq_dishes_source_suggestion_id constraint (both requests would pass an
    # unlocked SELECT-based check before either commits). Two separate AsyncClients so neither
    # request can be serialized behind the other's own connection.
    admin = await _login_as(client, db_session, UserRole.admin, "david")
    suggestion = await _create_suggestion(db_session, requested_by=admin.id)
    category_response = await client.post("/api/menu/categories", json={"name": "Pizza"})
    assert category_response.status_code == 201
    category_id = category_response.json()["id"]

    async def _confirm(http_client: AsyncClient, name: str) -> object:
        return await http_client.post(
            "/api/menu/dishes",
            json={"name": name, "price": "12.50", "category_id": category_id, "source_suggestion_id": suggestion.id},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as second_client:
        second_client.cookies.update(client.cookies)

        # Act
        first_response, second_response = await asyncio.gather(
            _confirm(client, "Flatbread A"), _confirm(second_client, "Flatbread B")
        )

    # Assert: exactly one confirms, the other loses the race and is rejected as a conflict, never
    # a 500 from an unhandled IntegrityError.
    statuses = sorted([first_response.status_code, second_response.status_code])
    assert statuses == [201, 409]


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


@pytest.mark.asyncio
async def test_dismissing_an_already_dismissed_suggestion_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    admin = await _login_as(client, db_session, UserRole.admin, "david")
    suggestion = await _create_suggestion(db_session, requested_by=admin.id, dismissed=True)

    # Act
    response = await client.post(f"/api/smart-chef/suggestions/{suggestion.id}/dismiss")

    # Assert
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_dismissing_an_already_confirmed_suggestion_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
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
    response = await client.post(f"/api/smart-chef/suggestions/{suggestion.id}/dismiss")

    # Assert
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_dismissing_a_nonexistent_suggestion_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.admin, "david")

    # Act
    response = await client.post("/api/smart-chef/suggestions/999999/dismiss")

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_suggestion_role_coverage(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange/Act/Assert: cook, waiter, warehouse_manager are all 403 (Admin-only); unauthenticated
    # is 401.
    admin_for_setup = await _login_as(client, db_session, UserRole.admin, "david")
    suggestion = await _create_suggestion(db_session, requested_by=admin_for_setup.id)

    await _login_as(client, db_session, UserRole.cook, "amir")
    assert (await client.post(f"/api/smart-chef/suggestions/{suggestion.id}/dismiss")).status_code == 403

    await _login_as(client, db_session, UserRole.waiter, "maya")
    assert (await client.post(f"/api/smart-chef/suggestions/{suggestion.id}/dismiss")).status_code == 403

    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    assert (await client.post(f"/api/smart-chef/suggestions/{suggestion.id}/dismiss")).status_code == 403

    client.cookies.clear()
    assert (await client.post(f"/api/smart-chef/suggestions/{suggestion.id}/dismiss")).status_code == 401


@pytest.mark.asyncio
async def test_llm_client_raises_a_plain_error_when_no_api_key_is_configured() -> None:
    # Arrange: an empty api_key is exactly what config.yaml falls back to when OPENAI_API_KEY is
    # unset — confirms this raises a plain, catchable error (which AIService already wraps into
    # a 502) rather than the OpenAI SDK's own construction-time error propagating raw (review
    # finding: AsyncOpenAI(api_key="") raises immediately at construction, confirmed empirically
    # against the installed SDK).
    client = LLMClient(api_key="", model="gpt-4o-mini")

    # Act/Assert
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
        await client.generate_recipe("irrelevant prompt")


# --- Story 6.3: Consult, Version, and Improve Recipes via Smart Assistant Chat ---------------


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
async def test_creating_a_chat_session_with_both_targets_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    cook = await _login_as(client, db_session, UserRole.cook, "amir")
    suggestion = await _create_suggestion(db_session, requested_by=cook.id)
    dish = await _create_dish(db_session, "Flatbread")

    # Act
    response = await client.post(
        "/api/smart-chef/chat-sessions", json={"dish_id": dish.id, "suggestion_id": suggestion.id}
    )

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_creating_a_chat_session_against_a_nonexistent_dish_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.post("/api/smart-chef/chat-sessions", json={"dish_id": 999999})

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_creating_a_chat_session_against_a_nonexistent_suggestion_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.post("/api/smart-chef/chat-sessions", json={"suggestion_id": 999999})

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_follow_up_message_gives_the_assistant_access_to_prior_turns_as_context(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: AC2 - the messages list passed to the LLM client on the second send must include
    # the first turn's actual content, not just the new message.
    await _login_as(client, db_session, UserRole.cook, "amir")
    dish = await _create_dish(db_session, "Flatbread")
    session_response = await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})
    session_id = session_response.json()["id"]

    first = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "What herbs would work well?"}
    )
    assert first.status_code == 201

    # Act
    second = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "What about basil specifically?"}
    )

    # Assert
    assert second.status_code == 201
    assert len(fake_llm_client.chat_calls) == 2
    second_call_contents = [m["content"] for m in fake_llm_client.chat_calls[1]]
    assert "What herbs would work well?" in second_call_contents
    assert fake_llm_client.chat_response in second_call_contents
    assert "What about basil specifically?" in second_call_contents


@pytest.mark.asyncio
async def test_a_session_created_by_one_cook_is_fully_readable_by_a_different_cook(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange (AC3): no special grant needed - shared access, sort-not-filter personalization.
    await _login_as(client, db_session, UserRole.cook, "amir")
    dish = await _create_dish(db_session, "Flatbread")
    session_response = await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})
    session_id = session_response.json()["id"]
    send_response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "Any tips?"}
    )
    assert send_response.status_code == 201

    # Act: a different Cook reads the same session and its messages.
    await _login_as(client, db_session, UserRole.cook, "noa")
    session_detail = await client.get("/api/smart-chef/chat-sessions")
    messages_response = await client.get(f"/api/smart-chef/chat-sessions/{session_id}/messages")

    # Assert
    assert session_id in [s["id"] for s in session_detail.json()]
    assert messages_response.status_code == 200
    assert len(messages_response.json()) == 2


@pytest.mark.asyncio
async def test_a_different_cook_can_send_a_message_into_a_session_they_did_not_create(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange (AC3): the write side, not just reads - continuing another Cook's session needs no
    # special grant either.
    await _login_as(client, db_session, UserRole.cook, "amir")
    dish = await _create_dish(db_session, "Flatbread")
    session_response = await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})
    session_id = session_response.json()["id"]

    # Act: a different Cook sends into the session amir created.
    await _login_as(client, db_session, UserRole.cook, "noa")
    send_response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "Any tips?"}
    )

    # Assert
    assert send_response.status_code == 201
    messages = send_response.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_an_empty_chat_reply_persists_no_messages_and_returns_502(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange (AC4): an empty-string reply from OpenAI must not be persisted as a valid message.
    await _login_as(client, db_session, UserRole.cook, "amir")
    dish = await _create_dish(db_session, "Flatbread")
    session_response = await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})
    session_id = session_response.json()["id"]
    fake_llm_client.chat_response = ""

    # Act
    response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "How do I improve this?"}
    )

    # Assert
    assert response.status_code == 502
    result = await db_session.execute(select(AIChatMessage).where(AIChatMessage.session_id == session_id))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_a_failed_chat_reply_persists_no_messages_and_returns_502(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange (AC4)
    await _login_as(client, db_session, UserRole.cook, "amir")
    dish = await _create_dish(db_session, "Flatbread")
    session_response = await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})
    session_id = session_response.json()["id"]
    fake_llm_client.chat_error = RuntimeError("simulated OpenAI failure")

    # Act
    response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "How do I improve this?"}
    )

    # Assert
    assert response.status_code == 502
    assert response.json()["detail"] == "Couldn't get a response right now"
    result = await db_session.execute(select(AIChatMessage).where(AIChatMessage.session_id == session_id))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_a_second_concurrent_send_into_the_same_session_is_rejected(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "amir")
    dish = await _create_dish(db_session, "Flatbread")
    session_response = await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})
    session_id = session_response.json()["id"]
    fake_llm_client.block_event = asyncio.Event()

    # Act
    first_task = asyncio.create_task(
        client.post(f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "First message"})
    )
    await asyncio.wait_for(fake_llm_client.chat_started.wait(), timeout=2)
    second_response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "Second message"}
    )
    fake_llm_client.block_event.set()
    first_response = await first_task

    # Assert
    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Rejected, a reply is already generating for this session"


@pytest.mark.asyncio
async def test_a_different_sessions_send_is_not_blocked_by_another_sessions_in_flight_send(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: the in-flight guard is keyed by session_id, so a send into a DIFFERENT session must
    # not be blocked by another session's own in-flight send.
    await _login_as(client, db_session, UserRole.cook, "amir")
    dish = await _create_dish(db_session, "Flatbread")
    first_session = (await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})).json()
    second_session = (await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})).json()
    fake_llm_client.block_event = asyncio.Event()

    # Act
    first_task = asyncio.create_task(
        client.post(
            f"/api/smart-chef/chat-sessions/{first_session['id']}/messages", json={"content": "First message"}
        )
    )
    await asyncio.wait_for(fake_llm_client.chat_started.wait(), timeout=2)
    second_response = await client.post(
        f"/api/smart-chef/chat-sessions/{second_session['id']}/messages", json={"content": "Second message"}
    )
    fake_llm_client.block_event.set()
    first_response = await first_task

    # Assert
    assert first_response.status_code == 201
    assert second_response.status_code == 201


@pytest.mark.asyncio
async def test_a_suggestion_chat_revision_request_updates_the_generated_recipe(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange (this batch's #7): the Cook asks for a change, the model returns an updated_recipe.
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
async def test_a_suggestion_chat_with_no_revision_requested_leaves_the_recipe_untouched(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: updated_recipe stays None (the FakeLLMClient's default), matching "just answer,
    # no revision requested".
    cook = await _login_as(client, db_session, UserRole.cook, "amir")
    suggestion = await _create_suggestion(db_session, requested_by=cook.id)
    suggestion_id = suggestion.id
    original_recipe = suggestion.generated_recipe
    session_id = (
        await client.post("/api/smart-chef/chat-sessions", json={"suggestion_id": suggestion_id})
    ).json()["id"]

    # Act
    response = await client.post(
        f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "What herbs would work well?"}
    )

    # Assert
    assert response.status_code == 201
    db_session.expire_all()
    saved = await db_session.get(AIRecipeSuggestion, suggestion_id)
    assert saved.generated_recipe == original_recipe


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


@pytest.mark.asyncio
async def test_two_sessions_on_the_same_suggestion_sending_concurrently_only_one_succeeds(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange: two different Chat Sessions both tied to the same Suggestion (e.g. two Cooks each
    # opening their own "Discuss via chat" thread on it) must not race an update to its
    # generated_recipe — _suggestion_chat_in_flight (keyed by suggestion id, independent of
    # _chat_in_flight's per-session guard) is what rejects the second.
    cook = await _login_as(client, db_session, UserRole.cook, "amir")
    suggestion = await _create_suggestion(db_session, requested_by=cook.id)
    first_session_id = (
        await client.post("/api/smart-chef/chat-sessions", json={"suggestion_id": suggestion.id})
    ).json()["id"]
    second_session_id = (
        await client.post("/api/smart-chef/chat-sessions", json={"suggestion_id": suggestion.id})
    ).json()["id"]
    fake_llm_client.block_event = asyncio.Event()

    # Act
    first_task = asyncio.create_task(
        client.post(
            f"/api/smart-chef/chat-sessions/{first_session_id}/messages", json={"content": "First message"}
        )
    )
    await asyncio.wait_for(fake_llm_client.chat_started.wait(), timeout=2)
    second_response = await client.post(
        f"/api/smart-chef/chat-sessions/{second_session_id}/messages", json={"content": "Second message"}
    )
    fake_llm_client.block_event.set()
    first_response = await first_task

    # Assert
    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Rejected, a reply is already generating for this session"


@pytest.mark.asyncio
async def test_three_sequential_messages_are_returned_in_ascending_chronological_order(
    client: AsyncClient, db_session: AsyncSession, fake_llm_client: FakeLLMClient
) -> None:
    # Arrange (AC5)
    await _login_as(client, db_session, UserRole.cook, "amir")
    dish = await _create_dish(db_session, "Flatbread")
    session_id = (await client.post("/api/smart-chef/chat-sessions", json={"dish_id": dish.id})).json()["id"]

    # Act
    for content in ("First", "Second", "Third"):
        response = await client.post(
            f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": content}
        )
        assert response.status_code == 201

    # Assert
    list_response = await client.get(f"/api/smart-chef/chat-sessions/{session_id}/messages")
    contents = [m["content"] for m in list_response.json() if m["role"] == "user"]
    assert contents == ["First", "Second", "Third"]


@pytest.mark.asyncio
async def test_get_chat_sessions_returns_empty_list_not_404(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange (AC6, backend side)
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/smart-chef/chat-sessions")

    # Assert
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_sending_a_message_to_a_nonexistent_session_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.post("/api/smart-chef/chat-sessions/999999/messages", json={"content": "hi"})

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_listing_messages_for_a_nonexistent_session_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange
    await _login_as(client, db_session, UserRole.cook, "amir")

    # Act
    response = await client.get("/api/smart-chef/chat-sessions/999999/messages")

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_chat_session_role_coverage(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange/Act/Assert: waiter, warehouse_manager, admin are all 403 (Cook-only, no admin
    # fallback); unauthenticated is 401.
    await _login_as(client, db_session, UserRole.waiter, "maya")
    assert (await client.post("/api/smart-chef/chat-sessions", json={"dish_id": 1})).status_code == 403

    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    assert (await client.post("/api/smart-chef/chat-sessions", json={"dish_id": 1})).status_code == 403

    await _login_as(client, db_session, UserRole.admin, "david")
    assert (await client.post("/api/smart-chef/chat-sessions", json={"dish_id": 1})).status_code == 403

    client.cookies.clear()
    assert (await client.post("/api/smart-chef/chat-sessions", json={"dish_id": 1})).status_code == 401


@pytest.mark.asyncio
async def test_send_chat_message_role_coverage(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange
    cook = await _login_as(client, db_session, UserRole.cook, "amir")
    suggestion = await _create_suggestion(db_session, requested_by=cook.id)
    session_id_row = AIChatSession(user_id=cook.id, suggestion_id=suggestion.id, title="Chat about test")
    db_session.add(session_id_row)
    await db_session.commit()
    await db_session.refresh(session_id_row)
    session_id = session_id_row.id

    # Act/Assert: waiter, warehouse_manager, admin are all 403 (Cook-only, no admin fallback);
    # unauthenticated is 401.
    await _login_as(client, db_session, UserRole.waiter, "maya")
    assert (
        await client.post(f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "hi"})
    ).status_code == 403

    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    assert (
        await client.post(f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "hi"})
    ).status_code == 403

    await _login_as(client, db_session, UserRole.admin, "david")
    assert (
        await client.post(f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "hi"})
    ).status_code == 403

    client.cookies.clear()
    assert (
        await client.post(f"/api/smart-chef/chat-sessions/{session_id}/messages", json={"content": "hi"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_list_chat_sessions_and_messages_role_coverage(client: AsyncClient, db_session: AsyncSession) -> None:
    # Arrange/Act/Assert: waiter and warehouse_manager are 403 on both read routes;
    # unauthenticated is 401. Admin CAN list (shared read, matching SmartChefReadDep).
    await _login_as(client, db_session, UserRole.waiter, "maya")
    assert (await client.get("/api/smart-chef/chat-sessions")).status_code == 403

    await _login_as(client, db_session, UserRole.warehouse_manager, "noa")
    assert (await client.get("/api/smart-chef/chat-sessions")).status_code == 403

    await _login_as(client, db_session, UserRole.admin, "david")
    assert (await client.get("/api/smart-chef/chat-sessions")).status_code == 200

    client.cookies.clear()
    assert (await client.get("/api/smart-chef/chat-sessions")).status_code == 401
