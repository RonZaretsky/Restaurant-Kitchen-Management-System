import asyncio

import pytest
import pytest_asyncio
from dependency_injector import providers
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import AIRecipeSuggestion, Ingredient, Unit, User, UserRole
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

    async def generate_recipe(self, prompt: str) -> dict:
        self.calls.append(prompt)
        if self.block_event is not None:
            await self.block_event.wait()
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


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
    # Arrange: the first call blocks on an event this test controls, so the "in flight" window is
    # deterministic rather than timing-dependent.
    await _create_ingredient(db_session, "Basil", "2.000", "1.000")
    await _login_as(client, db_session, UserRole.cook, "amir")
    fake_llm_client.block_event = asyncio.Event()

    # Act
    first_task = asyncio.create_task(client.post("/api/smart-chef/suggestions", json={}))
    await asyncio.sleep(0.1)  # let the first request actually reach the in-flight set
    second_response = await client.post("/api/smart-chef/suggestions", json={})
    fake_llm_client.block_event.set()
    first_response = await first_task

    # Assert
    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Rejected, a suggestion is already generating for this Cook"


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
