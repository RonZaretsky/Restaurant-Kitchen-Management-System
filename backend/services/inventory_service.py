from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import CreateIngredientRequest, CreateStockMovementRequest, Ingredient, MovementType, StockMovement, User
from exceptions import DuplicateIngredientNameError, IngredientNotFoundError


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
            # Logging before rollback, not after: rollback() expires every object
            # bound to this session, actor included, so reading actor.id afterward
            # raises an unhandled MissingGreenlet.
            self._logger.warning(
                "Ingredient creation rejected by user_id={}: name={} already exists (lost the race)",
                actor.id,
                payload.name,
            )
            await db.rollback()
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

    async def get_ingredient(self, db: AsyncSession, ingredient_id: int) -> Ingredient:
        """Fetch one Ingredient by id, for the Ingredient detail screen's stat cards.

        Args:
            db: The active database session.
            ingredient_id: The id of the Ingredient to fetch.

        Returns:
            The matching Ingredient.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        return await self._get_ingredient(db, ingredient_id)

    async def list_movements(self, db: AsyncSession, ingredient_id: int) -> Sequence[StockMovement]:
        """List every Stock Movement recorded for an Ingredient, newest first.

        Args:
            db: The active database session.
            ingredient_id: The id of the Ingredient whose history is being read.

        Returns:
            Every Stock Movement for this Ingredient, most recent first.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        await self._get_ingredient(db, ingredient_id)
        result = await db.execute(
            select(StockMovement)
            .where(StockMovement.ingredient_id == ingredient_id)
            .order_by(StockMovement.timestamp.desc(), StockMovement.id.desc())
        )
        return result.scalars().all()

    async def record_movement(
        self, db: AsyncSession, actor: User, ingredient_id: int, payload: CreateStockMovementRequest
    ) -> StockMovement:
        """Log a manual Stock Movement and update the Ingredient's current stock (AC1/AC2).

        Not a guarded UPDATE (trap 18 does not apply here): nothing about the Ingredient's own
        state blocks a movement the way an OrderItem's status blocks an edit. It is still a
        read-modify-write on current_stock, so the read locks the row (mirrors MenuService's
        _lock_dish, trap 9's shape): without the lock, two concurrent movements on the same
        Ingredient would both read the same starting current_stock and the later commit would
        silently discard the earlier delta, even though both StockMovement audit rows would still
        insert correctly, leaving current_stock disagreeing with its own audit trail (NFR-4). Both
        the Ingredient update and the new StockMovement insert commit together in one transaction
        (AD-16, NFR-4). purchase/waste apply as +/-quantity; adjustment applies payload.quantity as
        already signed. current_stock is never floor-capped at zero (AD-16): a waste or negative
        adjustment is applied in full even past zero.

        Args:
            db: The active database session.
            actor: The Warehouse Manager or Admin logging the movement.
            ingredient_id: The id of the Ingredient the movement applies to.
            payload: The submitted movement type, quantity, and optional note.

        Returns:
            The newly recorded Stock Movement.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        try:
            ingredient = await self._lock_ingredient(db, ingredient_id)
        except IngredientNotFoundError:
            self._logger.warning(
                "Stock movement rejected by user_id={}: ingredient_id={} not found",
                actor.id,
                ingredient_id,
            )
            raise

        delta = -payload.quantity if payload.movement_type == MovementType.waste else payload.quantity
        ingredient.current_stock = ingredient.current_stock + delta

        movement = StockMovement(
            ingredient_id=ingredient_id,
            movement_type=payload.movement_type,
            quantity_change=delta,
            performed_by=actor.id,
            notes=payload.notes,
        )
        db.add(movement)
        await db.commit()
        await db.refresh(movement)
        await db.refresh(ingredient)
        self._logger.info(
            "Stock movement recorded by user_id={}: ingredient_id={} type={} quantity_change={} new_stock={}",
            actor.id,
            ingredient_id,
            payload.movement_type.value,
            delta,
            ingredient.current_stock,
        )
        return movement

    async def _get_ingredient(self, db: AsyncSession, ingredient_id: int) -> Ingredient:
        """Fetch an Ingredient by id with no row lock, for read-only callers.

        Args:
            db: The active database session.
            ingredient_id: The id of the Ingredient to fetch.

        Returns:
            The matching Ingredient.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        ingredient = await db.get(Ingredient, ingredient_id)
        if ingredient is None:
            raise IngredientNotFoundError()
        return ingredient

    async def _lock_ingredient(self, db: AsyncSession, ingredient_id: int) -> Ingredient:
        """Lock an Ingredient row for the rest of the transaction and return it.

        record_movement reads current_stock and then writes a new value derived from it.
        Without a lock, two concurrent movements on the same Ingredient both read the same
        starting current_stock and the later commit silently overwrites the earlier delta, even
        though both StockMovement audit rows still insert correctly (mirrors MenuService._lock_dish,
        trap 9's shape: lock the one row every caller contends on, so they serialize instead of
        racing or deadlocking).

        Args:
            db: The active database session.
            ingredient_id: The id of the Ingredient to lock.

        Returns:
            The matching Ingredient, locked for this transaction.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        result = await db.execute(select(Ingredient).where(Ingredient.id == ingredient_id).with_for_update())
        ingredient = result.scalar_one_or_none()
        if ingredient is None:
            raise IngredientNotFoundError()
        return ingredient
