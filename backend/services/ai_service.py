from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clients.llm import LLMClient
from data_models import AIRecipeSuggestion, Ingredient, User
from exceptions import AIGenerationFailedError, SuggestionGenerationInProgressError

# A sentinel used to rank a zero-min_stock_threshold Ingredient as maximally "at risk of waste"
# (Scope note's heuristic) rather than falling back to its raw current_stock, which would mix an
# incomparable scale (a dimensionless ratio vs. a raw quantity) into the same sort (review
# finding). Any zero-threshold Ingredient with stock > 0 sorts ahead of every ratio-based one.
_ZERO_THRESHOLD_RANK = Decimal("Infinity")


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
        actually succeeds *and* returns the expected shape (AC4, FR-21) — a failure or a
        malformed response leaves no orphaned or partial row.

        Only Ingredients with `current_stock > 0` are snapshotted ("currently-available" stock,
        AC1) — an out-of-stock Ingredient contributes nothing to reduce waste. If none remain
        (nothing in stock at all), the request is rejected rather than prompting the model with an
        empty ingredient list, which risks a hallucinated, unusable suggestion (review finding).

        The stock snapshot is sorted by `_waste_risk_rank` descending: the most defensible
        available proxy for "at risk of waste" (FR-18), since nothing in this schema tracks
        expiry dates or usage rates. An Ingredient sitting at many times its own minimum
        threshold is the one most plausibly overstocked, not necessarily the one with the largest
        raw quantity.

        The parsed response's shape is validated before persisting (`name`/`ingredients`/
        `plating` present with the expected types) — a syntactically valid JSON object missing
        these would otherwise be persisted as a "successful" suggestion and only fail later at
        render time (review finding).

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
            AIGenerationFailedError: If there is nothing currently in stock, the OpenAI call
                fails or times out, or the response is missing the expected shape (AC4).
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
                # an empty ingredient list and risking a hallucinated, unusable suggestion
                # (review finding).
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

            prompt = self._build_prompt(snapshot, direction)

            try:
                generated_recipe = await self._llm_client.generate_recipe(prompt)
                if not isinstance(generated_recipe, dict) or not (
                    isinstance(generated_recipe.get("name"), str)
                    and isinstance(generated_recipe.get("ingredients"), list)
                    and isinstance(generated_recipe.get("plating"), str)
                ):
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
            return suggestion
        finally:
            self._in_flight.discard(actor.id)

    @staticmethod
    def _waste_risk_rank(ingredient: Ingredient) -> Decimal:
        """Rank an Ingredient by surplus relative to its own minimum threshold, descending.

        `current_stock / min_stock_threshold` for the normal case. A zero threshold cannot be
        divided by, but is not simply "current_stock" either (review finding) — mixing a
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
