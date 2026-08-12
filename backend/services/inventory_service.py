from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import CreateIngredientRequest, Ingredient, User
from exceptions import DuplicateIngredientNameError


class InventoryService:
    """Creates and manages Ingredient records.

    Config-free, so it is registered as a container-level Factory with only
    the logger injected. Per-request state such as the DB session is passed
    into each method as an argument, never held on the instance, matching
    UserService's shape.
    """

    def __init__(self, logger: Any) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
        """
        self._logger = logger

    async def list_ingredients(self, db: AsyncSession) -> Sequence[Ingredient]:
        """List every Ingredient.

        No actor argument: a plain unfiltered read has nothing to reject and
        nothing worth auditing, permissions are Role-level only.

        Args:
            db: The active database session.

        Returns:
            Every Ingredient row, in id order.
        """
        result = await db.execute(select(Ingredient).order_by(Ingredient.id))
        return result.scalars().all()

    async def create_ingredient(
        self, db: AsyncSession, actor: User, payload: CreateIngredientRequest
    ) -> Ingredient:
        """Create a new Ingredient record.

        Args:
            db: The active database session.
            actor: The Warehouse Manager or Admin performing the creation,
                used only for logging.
            payload: The submitted name, unit, threshold, and initial stock.

        Returns:
            The newly created Ingredient.

        Raises:
            DuplicateIngredientNameError: If the name already exists,
                compared without regard to case.
        """
        existing = await db.execute(
            select(Ingredient).where(func.lower(Ingredient.name) == payload.name.lower())
        )
        if existing.scalar_one_or_none() is not None:
            self._logger.warning(
                "Ingredient creation rejected by user_id={}: name={} already exists",
                actor.id,
                payload.name,
            )
            raise DuplicateIngredientNameError()

        ingredient = Ingredient(
            name=payload.name,
            unit=payload.unit,
            current_stock=payload.current_stock,
            min_stock_threshold=payload.min_stock_threshold,
        )
        db.add(ingredient)
        try:
            await db.commit()
        except IntegrityError as exc:
            # The check above loses to a concurrent create of the same name.
            # The unique index is the real arbiter, so translate its violation
            # into the same 409 rather than letting it surface as a 500.
            await db.rollback()
            self._logger.warning(
                "Ingredient creation rejected by user_id={}: name={} already exists (lost the race)",
                actor.id,
                payload.name,
            )
            raise DuplicateIngredientNameError() from exc
        await db.refresh(ingredient)
        self._logger.info(
            "Ingredient created by user_id={}: ingredient_id={} name={} unit={}",
            actor.id,
            ingredient.id,
            ingredient.name,
            ingredient.unit.value,
        )
        return ingredient
