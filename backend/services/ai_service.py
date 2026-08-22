from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clients.llm import LLMClient
from data_models import AIRecipeSuggestion, Ingredient, User
from exceptions import AIGenerationFailedError, SuggestionGenerationInProgressError


class AIService:
    """Generates AI Recipe Suggestions from current stock (Story 6.1, FR-18).

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
            llm_client: Injected client used to call OpenAI (AD-12) — this service never imports
                `openai` itself.
        """
        self._logger = logger
        self._llm_client = llm_client
        # In-process only (Story 6.1's AD-14 guard): the set of Cook user ids currently generating
        # a suggestion. Not persisted, not shared across processes — sufficient for this
        # single-process app, and simpler than a DB column or a distributed lock for a rule that
        # only needs to reject a second concurrent request, never queue or recover it.
        self._in_flight: set[int] = set()

    async def generate_suggestion(
        self, db: AsyncSession, actor: User, direction: str | None
    ) -> AIRecipeSuggestion:
        """Generate and persist a Recipe Suggestion from a snapshot of current stock (AC1, AC2).

        Rejects a second concurrent request from the same Cook immediately, before any DB read or
        OpenAI call (AC3, AD-14). No Recipe Suggestion row is ever created unless the OpenAI call
        actually succeeds (AC4, FR-21) — a failure leaves no orphaned or partial row.

        The stock snapshot is sorted by `current_stock / min_stock_threshold` descending: the
        most defensible available proxy for "at risk of waste" (FR-18), since nothing in this
        schema tracks expiry dates or usage rates. An Ingredient sitting at many times its own
        minimum threshold is the one most plausibly overstocked, not necessarily the one with the
        largest raw quantity (a staple with a big min_stock_threshold isn't "at risk" just
        because its current_stock number happens to be large too).

        Args:
            db: The active database session.
            actor: The Cook requesting the suggestion.
            direction: Optional free-text steering hint, folded into the prompt but never
                overriding the stock-availability constraint (AC2).

        Returns:
            The newly created, persisted Recipe Suggestion.

        Raises:
            SuggestionGenerationInProgressError: If a generation is already in flight for this
                Cook (AC3).
            AIGenerationFailedError: If the OpenAI call fails, times out, or returns unparseable
                content (AC4).
        """
        if actor.id in self._in_flight:
            self._logger.warning(
                "Recipe suggestion generation rejected for user_id={}: already in flight",
                actor.id,
            )
            raise SuggestionGenerationInProgressError()

        self._in_flight.add(actor.id)
        try:
            result = await db.execute(select(Ingredient))
            ingredients = result.scalars().all()
            sorted_ingredients = sorted(
                ingredients,
                key=lambda ingredient: (
                    ingredient.current_stock / ingredient.min_stock_threshold
                    if ingredient.min_stock_threshold
                    else ingredient.current_stock
                ),
                reverse=True,
            )
            snapshot = [
                {
                    "name": ingredient.name,
                    "unit": ingredient.unit.value,
                    "current_stock": str(ingredient.current_stock),
                }
                for ingredient in sorted_ingredients
            ]

            prompt = self._build_prompt(snapshot, direction)

            try:
                generated_recipe = await self._llm_client.generate_recipe(prompt)
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
            return suggestion
        finally:
            self._in_flight.discard(actor.id)

    async def list_suggestions(self, db: AsyncSession, actor: User) -> Sequence[AIRecipeSuggestion]:
        """List every Recipe Suggestion, newest first.

        No actor-based filtering (AD-9) — every Cook and Admin sees every suggestion; a
        "current Cook's own items first" sort, if ever added, belongs client-side (AD-10),
        matching this exact domain's own FR-20 precedent for Chat Sessions. `actor` is accepted
        only for signature symmetry with every other method in this service, unused otherwise,
        matching `OrderService.list_open_orders`'s own documented shape. No `dismissed` filter —
        that column does not exist until Story 6.2's own migration adds it.

        Args:
            db: The active database session.
            actor: The Cook or Admin making the request.

        Returns:
            Every Recipe Suggestion, ordered newest first.
        """
        result = await db.execute(select(AIRecipeSuggestion).order_by(AIRecipeSuggestion.id.desc()))
        return result.scalars().all()

    def _build_prompt(self, snapshot: list[dict[str, str]], direction: str | None) -> str:
        """Build the generation prompt from a stock snapshot and an optional direction (AC1, AC2).

        Args:
            snapshot: The stock snapshot, already sorted by surplus-relative-to-threshold
                descending — the order itself is the prioritization signal passed to the model.
            direction: Optional free-text steering hint.

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
        return (
            "You are a chef assistant for a restaurant kitchen. Propose exactly one recipe using "
            "only the ingredients listed below, prioritizing the ones listed first (they are the "
            "most overstocked relative to their normal minimum level, so using them helps reduce "
            "food waste).\n\n"
            f"Available ingredients (most at risk of waste first):\n{ingredients_text}"
            f"{direction_text}\n\n"
            'Respond with only a JSON object of this exact shape: {"name": "<dish name>", '
            '"ingredients": [{"name": "<ingredient name>", "quantity": "<amount with unit>"}], '
            '"plating": "<a short plating/serving description>"}.'
        )
