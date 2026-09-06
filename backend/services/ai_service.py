from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clients.llm import LLMClient
from data_models import (
    AIChatMessage,
    AIChatMessageResponse,
    AIChatSession,
    AIChatSessionResponse,
    AIRecipeSuggestion,
    AIRecipeSuggestionResponse,
    ChatRole,
    Dish,
    Ingredient,
    RecipeIngredient,
    Unit,
    User,
)
from exceptions import (
    AIChatReplyFailedError,
    AIGenerationFailedError,
    ChatMessageInProgressError,
    ChatSessionNotFoundError,
    DishNotFoundError,
    SuggestionAlreadyConfirmedError,
    SuggestionAlreadyDismissedError,
    SuggestionGenerationInProgressError,
    SuggestionNotFoundError,
)

# A sentinel used to rank a zero-min_stock_threshold Ingredient as maximally "at risk of waste"
# rather than falling back to its raw current_stock, which would mix an incomparable scale
# (a dimensionless ratio vs. a raw quantity) into the same sort. Any zero-threshold
# Ingredient with stock > 0 sorts ahead of every ratio-based one.
_ZERO_THRESHOLD_RANK = Decimal("Infinity")


class AIService:
    """Generates AI Recipe Suggestions from current stock.

    Config-free aside from its `llm_client`/`logger` collaborators, so it is registered as a
    container-level Factory, matching every other service's shape. `inventory_service` is
    deliberately NOT a dependency here — Ingredient stock is read directly via a plain `select()`,
    the same shape every other read-only service method in this codebase already uses; there is
    no stock *mutation* here for `InventoryService`'s machinery to be worth routing through.
    """

    def __init__(self, logger: Any, llm_client: LLMClient) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
            llm_client: Injected client used to call OpenAI — this service never imports
                `openai` itself.
        """
        self._logger = logger
        self._llm_client = llm_client
        # In-process only: the set of Cook user ids currently generating
        # a suggestion. Not persisted, not shared across processes — sufficient for this
        # single-process app, and simpler than a DB column or a distributed lock for a rule that
        # only needs to reject a second concurrent request, never queue or recover it.
        self._in_flight: set[int] = set()
        # A second, independent in-process guard, keyed by Chat Session id
        # rather than Cook user id: a Cook may legitimately have two different sessions open in
        # two tabs, but two concurrent sends into the *same* session would race the
        # message-ordering guarantee the chat relies on. Lives on this same Singleton, not a
        # container.py change — see this class's own Singleton reasoning above.
        self._chat_in_flight: set[int] = set()
        # A third in-process guard, keyed by Recipe Suggestion id rather
        # than session id: today's _chat_in_flight alone does not stop two *different* Chat
        # Sessions both tied to the *same* Suggestion from racing to overwrite its
        # generated_recipe (e.g. two Cooks each opening their own "Discuss via chat" thread on
        # it). Checked/reserved alongside _chat_in_flight only when a session targets a
        # Suggestion, released in the same finally — same "reject, don't queue" philosophy.
        self._suggestion_chat_in_flight: set[int] = set()

    async def generate_suggestion(
        self, db: AsyncSession, actor: User, direction: str | None, prioritize_waste: bool = False
    ) -> AIRecipeSuggestionResponse:
        """Generate and persist a Recipe Suggestion from a snapshot of current stock.

        Rejects a second concurrent request from the same Cook immediately, before any DB read or
        OpenAI call. No Recipe Suggestion row is ever created unless the OpenAI call
        actually succeeds *and* returns the expected shape — a failure or a
        malformed response leaves no orphaned or partial row.

        Only Ingredients with `current_stock > 0` are snapshotted ("currently-available" stock,
        only) — an out-of-stock Ingredient contributes nothing to reduce waste. If none remain
        (nothing in stock at all), the request is rejected rather than prompting the model with an
        empty ingredient list, which risks a hallucinated, unusable suggestion.

        The stock snapshot is sorted by `_waste_risk_rank` descending: the most defensible
        available proxy for "at risk of waste", since nothing in this schema tracks
        expiry dates or usage rates. An Ingredient sitting at many times its own minimum
        threshold is the one most plausibly overstocked, not necessarily the one with the largest
        raw quantity.

        The parsed response's shape is validated before persisting (`name`/`ingredients`/
        `plating` present with the expected types) — a syntactically valid JSON object missing
        these would otherwise be persisted as a "successful" suggestion and only fail later at
        render time.

        Args:
            db: The active database session.
            actor: The Cook requesting the suggestion.
            direction: Optional free-text steering hint, folded into the prompt but never
                overriding the stock-availability constraint.
            prioritize_waste: Opt-in (default off, manual-test feedback): when True, folds the
                waste-reduction framing back into the prompt (steer toward the most-overstocked
                ingredients, listed first in `snapshot`) — off by default because that framing
                made repeated suggestions converge on the same few ingredients every time.

        Returns:
            The newly created, persisted Recipe Suggestion.

        Raises:
            SuggestionGenerationInProgressError: If a generation is already in flight for this
                Cook.
            AIGenerationFailedError: If there is nothing currently in stock, the OpenAI call
                fails or times out, or the response is missing the expected shape.
        """
        if actor.id in self._in_flight:
            self._logger.warning(
                "Recipe suggestion generation rejected for user_id={}: already in flight",
                actor.id,
            )
            raise SuggestionGenerationInProgressError()

        self._in_flight.add(actor.id)
        try:
            result = await db.execute(select(Ingredient).where(Ingredient.current_stock > 0))
            ingredients = result.scalars().all()
            if not ingredients:
                # Nothing to build a recipe from — reject cleanly rather than sending the model
                # an empty ingredient list and risking a hallucinated, unusable suggestion.
                self._logger.warning(
                    "Recipe suggestion generation rejected for user_id={}: no ingredients in stock",
                    actor.id,
                )
                raise AIGenerationFailedError()

            sorted_ingredients = sorted(ingredients, key=self._waste_risk_rank, reverse=True)
            snapshot = [
                {
                    "name": ingredient.name,
                    "unit": ingredient.unit.value,
                    "current_stock": str(ingredient.current_stock),
                }
                for ingredient in sorted_ingredients
            ]

            prompt = self._build_prompt(snapshot, direction, prioritize_waste)

            try:
                generated_recipe = await self._llm_client.generate_recipe(prompt)
                if not self._is_recipe_shape_valid(generated_recipe):
                    raise ValueError("generated_recipe missing expected name/ingredients/plating shape")
            except Exception:
                self._logger.error(
                    "Recipe suggestion generation failed for user_id={}: OpenAI call failed",
                    actor.id,
                )
                raise AIGenerationFailedError() from None

            suggestion = AIRecipeSuggestion(
                requested_by=actor.id,
                prompt_used=prompt,
                generated_recipe=generated_recipe,
                ingredients_snapshot=snapshot,
            )
            db.add(suggestion)
            await db.commit()
            await db.refresh(suggestion)
            self._logger.info(
                "Recipe suggestion generated by user_id={}: suggestion_id={}",
                actor.id,
                suggestion.id,
            )
            # A freshly generated suggestion can never already be confirmed — Dish creation
            # always happens in a later, separate request.
            return AIRecipeSuggestionResponse.from_row(suggestion, confirmed_dish_id=None)
        finally:
            self._in_flight.discard(actor.id)

    @staticmethod
    def _is_recipe_shape_valid(recipe: object) -> bool:
        """Validate a parsed recipe's shape (name/ingredients/plating present with the expected
        types), shared by every write path that can persist a `generated_recipe` value —
        `generate_suggestion`'s own OpenAI response and `send_message`'s
        chat-driven `updated_recipe` — so the two can never drift into different
        validation rules.

        Args:
            recipe: The parsed value to validate. Typed as `object`, not `dict`, since it comes
                straight from parsed JSON and is not guaranteed to even be a dict.

        Returns:
            True if recipe is a dict with a "name" string, an "ingredients" list, and a
            "plating" string; False otherwise.
        """
        return (
            isinstance(recipe, dict)
            and isinstance(recipe.get("name"), str)
            and isinstance(recipe.get("ingredients"), list)
            and isinstance(recipe.get("plating"), str)
        )

    @staticmethod
    def _waste_risk_rank(ingredient: Ingredient) -> Decimal:
        """Rank an Ingredient by surplus relative to its own minimum threshold, descending.

        `current_stock / min_stock_threshold` for the normal case. A zero threshold cannot be
        divided by, but is not simply "current_stock" either — mixing a
        dimensionless ratio and a raw quantity in the same sort produces a meaningless order once
        both kinds of Ingredient are present. A zero-threshold Ingredient with any stock at all is
        instead ranked as maximally at-risk (there is no meaningful "normal" level for it to be
        measured against, so any stock is surplus); one with zero stock too ranks at the bottom,
        the same as every other empty Ingredient.

        Args:
            ingredient: The Ingredient to rank.

        Returns:
            A Decimal usable as a descending sort key.
        """
        if ingredient.min_stock_threshold:
            return ingredient.current_stock / ingredient.min_stock_threshold
        return _ZERO_THRESHOLD_RANK if ingredient.current_stock > 0 else Decimal("0")

    async def list_suggestions(self, db: AsyncSession, actor: User) -> Sequence[AIRecipeSuggestionResponse]:
        """List every Recipe Suggestion, newest first, each carrying its derived confirmed state.

        No actor-based filtering — every Cook and Admin sees every suggestion; a
        "current Cook's own items first" sort, if ever added, belongs client-side,
        matching this domain's own precedent for Chat Sessions. `actor` is accepted
        only for signature symmetry with every other method in this service, unused otherwise,
        matching `OrderService.list_open_orders`'s own documented shape.

        No `dismissed` filter here — same as before, this method returns every
        suggestion regardless of dismissed/confirmed state; "awaiting review" filtering is a
        client-side concern (`RecipeSuggestionsPage.tsx`), matching this codebase's established
        client-side-filter convention.

        A left join against `Dish.source_suggestion_id` resolves each row's `confirmed_dish_id`
        in one query, not one extra query per suggestion (no N+1) — "confirmed" is derived, not a
        stored column (see `AIRecipeSuggestion`'s own docstring).

        Args:
            db: The active database session.
            actor: The Cook or Admin making the request.

        Returns:
            Every Recipe Suggestion, ordered newest first.
        """
        result = await db.execute(
            select(AIRecipeSuggestion, Dish.id)
            .outerjoin(Dish, Dish.source_suggestion_id == AIRecipeSuggestion.id)
            .order_by(AIRecipeSuggestion.id.desc())
        )
        return [
            AIRecipeSuggestionResponse.from_row(suggestion, confirmed_dish_id=dish_id)
            for suggestion, dish_id in result.all()
        ]

    async def dismiss_suggestion(self, db: AsyncSession, actor: User, suggestion_id: int) -> AIRecipeSuggestionResponse:
        """Dismiss a Recipe Suggestion, retaining it for audit.

        Rejects a suggestion that is already dismissed or already confirmed (has a Dish citing it
        as its source) — dismissing and confirming are mutually exclusive terminal states, plain
        business-rule checks here, not schema constraints.

        Args:
            db: The active database session.
            actor: The Admin dismissing the suggestion.
            suggestion_id: The id of the Recipe Suggestion to dismiss.

        Returns:
            The now-dismissed Recipe Suggestion.

        Raises:
            SuggestionNotFoundError: If no Recipe Suggestion matches suggestion_id.
            SuggestionAlreadyDismissedError: If the suggestion is already dismissed.
            SuggestionAlreadyConfirmedError: If a Dish already cites this suggestion as its
                source.
        """
        suggestion = await db.get(AIRecipeSuggestion, suggestion_id)
        if suggestion is None:
            self._logger.warning(
                "Recipe suggestion dismiss rejected for user_id={}: no suggestion_id={}",
                actor.id,
                suggestion_id,
            )
            raise SuggestionNotFoundError()

        if suggestion.dismissed:
            self._logger.warning(
                "Recipe suggestion dismiss rejected for user_id={}: suggestion_id={} already dismissed",
                actor.id,
                suggestion_id,
            )
            raise SuggestionAlreadyDismissedError()

        confirmed_dish_id = await self._get_confirmed_dish_id(db, suggestion_id)
        if confirmed_dish_id is not None:
            self._logger.warning(
                "Recipe suggestion dismiss rejected for user_id={}: suggestion_id={} already confirmed"
                " (dish_id={})",
                actor.id,
                suggestion_id,
                confirmed_dish_id,
            )
            raise SuggestionAlreadyConfirmedError()

        suggestion.dismissed = True
        await db.commit()
        await db.refresh(suggestion)
        self._logger.info(
            "Recipe suggestion dismissed by user_id={}: suggestion_id={}",
            actor.id,
            suggestion_id,
        )
        # Reuses the same lookup rather than hardcoding None: the guard
        # above already rejects the confirmed case, but computing it here instead of assuming it
        # removes a fragile coupling to that guard never being reordered or relaxed later.
        return AIRecipeSuggestionResponse.from_row(suggestion, confirmed_dish_id=confirmed_dish_id)

    @staticmethod
    async def _get_confirmed_dish_id(db: AsyncSession, suggestion_id: int) -> int | None:
        """Look up the Dish (if any) that cites the given Recipe Suggestion as its source.

        Args:
            db: The active database session.
            suggestion_id: The Recipe Suggestion id to check.

        Returns:
            That Dish's id, or None if no Dish references this suggestion yet.
        """
        result = await db.execute(select(Dish.id).where(Dish.source_suggestion_id == suggestion_id))
        return result.scalar_one_or_none()

    def _build_prompt(
        self, snapshot: list[dict[str, str]], direction: str | None, prioritize_waste: bool = False
    ) -> str:
        """Build the generation prompt from a stock snapshot and an optional direction.

        No waste-priority steering in the prompt by default (per manual-test feedback: it made the
        model anchor on the same few overstocked ingredients across separate suggestions instead
        of proposing something different each time) — `direction`, when given, is otherwise the
        only steering signal. `prioritize_waste` opts back into that framing per request (this
        batch's own checkbox); `snapshot`'s surplus-relative-to-threshold ordering is retained on
        the persisted row regardless, for audit purposes, but only shapes the prompt when the flag
        is set.

        Args:
            snapshot: The stock snapshot to list as available ingredients.
            direction: Optional free-text steering hint.
            prioritize_waste: When True, steers the model toward the ingredients listed first in
                `snapshot` (the most overstocked relative to their own minimum threshold).

        Returns:
            The full prompt to send to the LLM client.
        """
        ingredients_text = "\n".join(
            f"- {item['name']}: {item['current_stock']} {item['unit']}" for item in snapshot
        )
        direction_text = (
            f'\n\nThe cook additionally asked for this direction: "{direction}". Use it to steer '
            "the suggestion, but never include an ingredient that is not listed above."
            if direction
            else ""
        )
        priority_text = (
            " Prioritize the ingredients listed first — they are the most overstocked relative to "
            "their normal minimum level, so using them helps reduce food waste."
            if prioritize_waste
            else ""
        )
        return (
            "You are a chef assistant for a restaurant kitchen. Propose exactly one recipe, sized for "
            "a single portion (one serving) only, using only the ingredients listed below — in "
            "whatever quantity one portion actually needs, never anywhere close to the full "
            f"available stock.{priority_text}\n\n"
            f"Available ingredients:\n{ingredients_text}"
            f"{direction_text}\n\n"
            'Respond with only a JSON object of this exact shape: {"name": "<dish name>", '
            '"ingredients": [{"name": "<ingredient name>", "quantity": "<decimal amount followed by '
            "the exact same unit shown for that ingredient above (kg, liter, or piece) — e.g. "
            '\\"0.2 kg\\", never grams or milliliters, sized for a single portion>"}], '
            '"plating": "<a short plating/serving description>"}.'
        )

    async def create_chat_session(
        self, db: AsyncSession, actor: User, dish_id: int | None, suggestion_id: int | None
    ) -> AIChatSessionResponse:
        """Open a new Chat Session tied to a Dish or a Recipe Suggestion.

        Exactly one of `dish_id`/`suggestion_id` is guaranteed non-None by
        `CreateChatSessionRequest`'s own model_validator — this method still only receives
        whichever the caller resolved, no re-validation of the XOR here (that is the schema's
        job, not the service's).

        `title` is server-computed at creation, not Cook-supplied: a snapshot of the
        target's name at this instant, matching `OrderItem.price_at_add`/
        `AIRecipeSuggestion.prompt_used`'s own "captured at creation time" precedent, so it stays
        stable even if the underlying Dish is later renamed.

        Args:
            db: The active database session.
            actor: The Cook opening the session.
            dish_id: The Dish this session targets, or None if targeting a Suggestion instead.
            suggestion_id: The Recipe Suggestion this session targets, or None if targeting a
                Dish instead.

        Returns:
            The newly created, persisted Chat Session.

        Raises:
            DishNotFoundError: If dish_id is set but no matching Dish exists.
            SuggestionNotFoundError: If suggestion_id is set but no matching Recipe Suggestion
                exists.
        """
        if dish_id is not None:
            dish = await db.get(Dish, dish_id)
            if dish is None:
                self._logger.warning(
                    "Chat session creation rejected for user_id={}: no dish_id={}", actor.id, dish_id
                )
                raise DishNotFoundError()
            title = f"Chat about {dish.name}"
            session = AIChatSession(user_id=actor.id, dish_id=dish_id, suggestion_id=None, title=title)
        else:
            suggestion = await db.get(AIRecipeSuggestion, suggestion_id)
            if suggestion is None:
                self._logger.warning(
                    "Chat session creation rejected for user_id={}: no suggestion_id={}",
                    actor.id,
                    suggestion_id,
                )
                raise SuggestionNotFoundError()
            title = f"Chat about {suggestion.generated_recipe['name']}"
            session = AIChatSession(user_id=actor.id, dish_id=None, suggestion_id=suggestion_id, title=title)

        db.add(session)
        await db.commit()
        await db.refresh(session)
        self._logger.info(
            "Chat session created by user_id={}: session_id={}, dish_id={}, suggestion_id={}",
            actor.id,
            session.id,
            dish_id,
            suggestion_id,
        )
        return AIChatSessionResponse.model_validate(session)

    async def list_chat_sessions(self, db: AsyncSession, actor: User) -> Sequence[AIChatSessionResponse]:
        """List every Chat Session, newest first.

        No actor-based filtering — every Cook and Admin sees every session; "current
        Cook's own items first" is a client-side sort, matching `list_suggestions`'s own
        precedent exactly. `actor` is accepted only for signature symmetry.

        Args:
            db: The active database session.
            actor: The Cook or Admin making the request.

        Returns:
            Every Chat Session, ordered newest first.
        """
        result = await db.execute(select(AIChatSession).order_by(AIChatSession.id.desc()))
        return [AIChatSessionResponse.model_validate(session) for session in result.scalars().all()]

    async def list_chat_messages(
        self, db: AsyncSession, actor: User, session_id: int
    ) -> Sequence[AIChatMessageResponse]:
        """List every Message in a Chat Session, in chronological order.

        Ascending, unlike `list_suggestions`'/`list_chat_sessions`'s own newest-first descending
        order — scrolling back through history reads as a conversation, oldest first.

        Args:
            db: The active database session.
            actor: The Cook or Admin making the request.
            session_id: The Chat Session whose messages are being listed.

        Returns:
            Every Message in the session, oldest first.

        Raises:
            ChatSessionNotFoundError: If no Chat Session matches session_id.
        """
        session = await db.get(AIChatSession, session_id)
        if session is None:
            raise ChatSessionNotFoundError()

        return await self._list_messages_ascending(db, session_id)

    async def send_message(
        self, db: AsyncSession, actor: User, session_id: int, content: str
    ) -> Sequence[AIChatMessageResponse]:
        """Send a Cook's message into a Chat Session and persist the assistant's reply.

        Message-pair atomicity: neither the user's
        own Message row nor the assistant's reply is inserted until the OpenAI call succeeds —
        both are inserted together, in one transaction, only on success. A looser reading would
        persist the user's message immediately and only skip the assistant reply on failure, but
        this is the one that keeps every session free of an unanswered dangling turn and matches
        `generate_suggestion`'s own insert-only-after-success shape exactly, rather than inventing
        a second failure semantics for this domain.

        Rejects a second concurrent send into the *same* session immediately (the prior
        messages sent as conversational context would otherwise race), before any OpenAI call
        (`_chat_in_flight`, keyed by session id, independent of `_in_flight`'s per-Cook guard).
        A Suggestion-tied session additionally checks `_suggestion_chat_in_flight` (keyed by
        Suggestion id): two *different* sessions tied to the *same* Suggestion
        must not both be allowed to race an update to its `generated_recipe`, which
        `_chat_in_flight` alone (keyed by session id) does not prevent.

        The system message is built from the target's *current* state on every send (a live
        read, never a value captured once at session-creation) — if a Dish's recipe changes
        mid-conversation, the next message the assistant answers reflects the current recipe.

        Branches on `session.suggestion_id is not None`: a Suggestion-tied session calls
        `LLMClient.send_chat_message_with_recipe_update`, requesting a JSON envelope
        (`{"reply": ..., "updated_recipe": ...}`, see `_build_chat_system_message`'s Suggestion
        branch) and validating `updated_recipe`, when not null, against the exact same shape
        check `generate_suggestion` uses (`_is_recipe_shape_valid`), so the two write paths can
        never drift into different validation rules. If present, the Suggestion's
        `generated_recipe` is reassigned (a plain `JSON` column, not `MutableDict`-wrapped, so
        SQLAlchemy only detects a full attribute reassignment, never an in-place mutation) before
        the two new Messages are added, so the single `db.commit()` below covers all three writes
        atomically. A Dish-tied session is unchanged: it still calls `send_chat_message`, the
        free-text contract.

        Args:
            db: The active database session.
            actor: The Cook sending the message.
            session_id: The Chat Session to send into.
            content: The Cook's message content.

        Returns:
            The two newly persisted Messages, user then assistant, matching insertion order.

        Raises:
            ChatSessionNotFoundError: If no Chat Session matches session_id.
            ChatMessageInProgressError: If a reply is already generating for this session, or (for
                a Suggestion-tied session) for another session tied to the same Suggestion.
            AIChatReplyFailedError: If the OpenAI call fails, times out, errors, or (for a
                Suggestion-tied session) returns a malformed envelope or updated_recipe.
        """
        session = await db.get(AIChatSession, session_id)
        if session is None:
            raise ChatSessionNotFoundError()

        is_suggestion_chat = session.suggestion_id is not None

        if session_id in self._chat_in_flight:
            self._logger.warning(
                "Chat message rejected for user_id={}: session_id={} already in flight",
                actor.id,
                session_id,
            )
            raise ChatMessageInProgressError()

        if is_suggestion_chat and session.suggestion_id in self._suggestion_chat_in_flight:
            self._logger.warning(
                "Chat message rejected for user_id={}: session_id={} suggestion_id={} already"
                " in flight for another session",
                actor.id,
                session_id,
                session.suggestion_id,
            )
            raise ChatMessageInProgressError()

        self._chat_in_flight.add(session_id)
        if is_suggestion_chat:
            self._suggestion_chat_in_flight.add(session.suggestion_id)
        try:
            dish: Dish | None = None
            suggestion: AIRecipeSuggestion | None = None
            recipe_lines: Sequence[tuple[str, Decimal, Unit]] | None = None
            available_ingredients: Sequence[Ingredient] | None = None

            if session.dish_id is not None:
                dish = await db.get(Dish, session.dish_id)
                lines_result = await db.execute(
                    select(Ingredient.name, RecipeIngredient.quantity, RecipeIngredient.unit)
                    .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
                    .where(RecipeIngredient.dish_id == session.dish_id)
                )
                recipe_lines = lines_result.all()
            else:
                suggestion = await db.get(AIRecipeSuggestion, session.suggestion_id)
                # A live read (not the suggestion's own `ingredients_snapshot`, which is frozen at
                # generation time) — a chat can happen long after generation, and stock may
                # have moved since. Constrains `updated_recipe` to what is actually available right
                # now, the same rule `generate_suggestion`'s own prompt already enforces.
                stock_result = await db.execute(select(Ingredient).where(Ingredient.current_stock > 0))
                available_ingredients = stock_result.scalars().all()

            system_message = self._build_chat_system_message(dish, suggestion, recipe_lines, available_ingredients)
            prior_messages = await self._list_messages_ascending(db, session_id)

            messages = [system_message]
            messages.extend({"role": message.role.value, "content": message.content} for message in prior_messages)
            messages.append({"role": "user", "content": content})

            updated_recipe: dict | None = None
            try:
                if is_suggestion_chat:
                    envelope = await self._llm_client.send_chat_message_with_recipe_update(messages)
                    if not isinstance(envelope, dict):
                        raise ValueError("chat envelope missing expected reply/updated_recipe shape")
                    reply = envelope.get("reply")
                    if not isinstance(reply, str) or not reply.strip():
                        raise ValueError("chat reply missing expected non-empty text content")
                    raw_updated_recipe = envelope.get("updated_recipe")
                    if raw_updated_recipe is not None:
                        if not self._is_recipe_shape_valid(raw_updated_recipe):
                            raise ValueError("updated_recipe missing expected name/ingredients/plating shape")
                        updated_recipe = raw_updated_recipe
                else:
                    reply = await self._llm_client.send_chat_message(messages)
                    if not isinstance(reply, str) or not reply.strip():
                        raise ValueError("chat reply missing expected non-empty text content")
            except Exception as exc:
                self._logger.error(
                    "Chat message failed for user_id={}: session_id={}: {}",
                    actor.id,
                    session_id,
                    exc,
                )
                raise AIChatReplyFailedError() from None

            user_message = AIChatMessage(session_id=session_id, role=ChatRole.user, content=content)
            assistant_message = AIChatMessage(session_id=session_id, role=ChatRole.assistant, content=reply)
            db.add(user_message)
            db.add(assistant_message)
            if updated_recipe is not None:
                assert suggestion is not None  # only set when is_suggestion_chat, which gates updated_recipe
                suggestion.generated_recipe = updated_recipe
            await db.commit()
            await db.refresh(user_message)
            await db.refresh(assistant_message)
            self._logger.info(
                "Chat message sent by user_id={}: session_id={} recipe_updated={}",
                actor.id,
                session_id,
                updated_recipe is not None,
            )
            return [
                AIChatMessageResponse.model_validate(user_message),
                AIChatMessageResponse.model_validate(assistant_message),
            ]
        finally:
            self._chat_in_flight.discard(session_id)
            if is_suggestion_chat:
                self._suggestion_chat_in_flight.discard(session.suggestion_id)

    @staticmethod
    async def _list_messages_ascending(db: AsyncSession, session_id: int) -> Sequence[AIChatMessage]:
        """Load every Message for a Chat Session, oldest first.

        A shared private seam so `list_chat_messages` and `send_message` (building the prior
        conversational context) never duplicate this query's shape.

        Args:
            db: The active database session.
            session_id: The Chat Session whose messages are being loaded.

        Returns:
            Every Message row for the session, ordered oldest first.
        """
        result = await db.execute(
            select(AIChatMessage).where(AIChatMessage.session_id == session_id).order_by(AIChatMessage.id.asc())
        )
        return result.scalars().all()

    def _build_chat_system_message(
        self,
        dish: Dish | None,
        suggestion: AIRecipeSuggestion | None,
        recipe_lines: Sequence[tuple[str, Decimal, Unit]] | None,
        available_ingredients: Sequence[Ingredient] | None = None,
    ) -> dict[str, str]:
        """Build the system message describing the chat's target recipe.

        Instructs the model it is a chef assistant discussing a specific recipe (naming it) and
        states the recipe's current ingredients/plating so it can reason about it. The Dish
        branch asks for plain conversational replies (no JSON mode, a system-message instruction
        rather than `response_format` — a Dish is a live orderable menu item, bigger blast
        radius, so its chat stays discussion-only). The Suggestion branch instead requests a JSON
        envelope (mirroring `_build_prompt`'s own "Respond with only a JSON object" wording),
        since `send_message` calls `LLMClient.send_chat_message_with_recipe_update` (JSON mode)
        only for a Suggestion-tied session, letting the Cook ask for a recipe change and have it
        applied in the same turn.

        Args:
            dish: The Dish this session targets, or None if it targets a Suggestion instead.
            suggestion: The Recipe Suggestion this session targets, or None if it targets a Dish
                instead.
            recipe_lines: The Dish's current Recipe Ingredient lines as (ingredient name,
                quantity, unit) tuples, or None when the target is a Suggestion.
            available_ingredients: The live, currently-in-stock Ingredients, used only in the
                Suggestion branch to constrain `updated_recipe` to what is actually available and
                to state each one's real unit (the "never include an ingredient that is not
                listed" rule, mirrored from `_build_prompt`) — None in the Dish branch, which
                never produces an `updated_recipe`.

        Returns:
            The system message to prepend to the OpenAI chat request.
        """
        off_topic_guard = (
            "Only discuss topics related to this recipe and cooking it — ingredients, quantities, "
            "preparation, substitutions, plating, nutrition. If the Cook's message is not related to "
            "this recipe or cooking, politely decline and steer the conversation back to the recipe "
            "instead of answering it."
        )
        if dish is not None:
            ingredients_text = (
                "\n".join(f"- {name}: {quantity} {unit.value}" for name, quantity, unit in recipe_lines)
                if recipe_lines
                else "(no recipe ingredients defined yet)"
            )
            description_text = f"\nDescription: {dish.description}" if dish.description else ""
            content = (
                f'You are a chef assistant discussing the recipe for "{dish.name}", a Dish on the '
                f"menu.{description_text}\n\nCurrent recipe ingredients:\n{ingredients_text}\n\n"
                "Discuss and help improve this recipe conversationally. Reply in plain text, not "
                f"JSON. {off_topic_guard}"
            )
        else:
            recipe = suggestion.generated_recipe
            ingredients_text = "\n".join(
                f"- {item.get('name')}: {item.get('quantity')}" for item in recipe.get("ingredients", [])
            )
            stock_text = "\n".join(
                f"- {ingredient.name}: {ingredient.current_stock} {ingredient.unit.value}"
                for ingredient in (available_ingredients or [])
            )
            content = (
                f'You are a chef assistant discussing a proposed recipe, "{recipe.get("name")}", a '
                "Recipe Suggestion not yet confirmed into a Dish.\n\n"
                f"Ingredients:\n{ingredients_text}\n\nPlating: {recipe.get('plating')}\n\n"
                f"Ingredients currently in stock (the only ones updated_recipe may ever use):\n"
                f"{stock_text}\n\n"
                'Respond with only a JSON object of this exact shape: {"reply": "<conversational '
                'reply text>", "updated_recipe": null or {"name": "<dish name>", "ingredients": '
                '[{"name": ..., "quantity": ...}], "plating": "<...>"}}. Set updated_recipe only '
                "if the Cook's message asks for a change to the recipe; otherwise set it to null "
                "and just answer in reply. When you do set it: the recipe stays sized for a single "
                "portion (one serving) only, every ingredient must come from the stock list above "
                "(never invent one that is not listed), and every quantity is a decimal amount in "
                'that exact same unit (kg, liter, or piece) — e.g. "0.15 kg", never grams or '
                f"milliliters. {off_topic_guard}"
            )
        return {"role": "system", "content": content}
