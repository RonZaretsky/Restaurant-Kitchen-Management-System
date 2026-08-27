from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import CreateIngredientRequest, CreateStockMovementRequest, Ingredient, MovementType, StockMovement, User, UserRole
from exceptions import (
    DuplicateIngredientNameError,
    IngredientNotActiveError,
    IngredientNotFoundError,
    InsufficientStockError,
    StockMovementWouldGoNegativeError,
)
from services.realtime_service import RealtimeService


class InventoryService:
    """Creates and manages Ingredient records.

    Config-free apart from realtime_service, so it is registered as a
    container-level Factory with the logger and realtime_service injected.
    Per-request state such as the DB session is passed into each method as an
    argument, never held on the instance, matching UserService's shape.
    """

    def __init__(self, logger: Any, realtime_service: RealtimeService) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
            realtime_service: Injected push-notification service, used to
                broadcast inventory.alerts_changed when a Stock Movement
                crosses an Ingredient's shortage threshold in either
                direction (Story 4.2).
        """
        self._logger = logger
        self._realtime_service = realtime_service

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

    async def list_alerts(self, db: AsyncSession) -> Sequence[Ingredient]:
        """List every Ingredient currently in shortage (FR-14).

        A Low-Stock Alert is a derived state, not a stored entity (see the
        story's Scope note): an Ingredient is "in shortage" whenever its
        current_stock is strictly below its min_stock_threshold, computed
        fresh on every call. There is nothing to create, dedupe, or clear —
        at most one row per Ingredient exists to begin with, so "at most one
        active alert per Ingredient" and "no manual dismiss" both hold by
        construction.

        Args:
            db: The active database session.

        Returns:
            Every Ingredient currently below its own min_stock_threshold,
            ordered by name.
        """
        result = await db.execute(
            select(Ingredient)
            .where(Ingredient.current_stock < Ingredient.min_stock_threshold)
            .order_by(Ingredient.name)
        )
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

    async def deactivate_ingredient(self, db: AsyncSession, actor: User, ingredient_id: int) -> Ingredient:
        """Deactivate an active Ingredient, blocking new Recipe Ingredient lines and new Stock
        Movements against it (Story #3/#4).

        Mirrors UserService.deactivate_user exactly: a simple flag flip, idempotent (a no-op on
        an already-inactive Ingredient), no row-locking needed (this isn't a numeric
        read-modify-write like record_movement). Historical Recipe Ingredient lines and Stock
        Movements referencing this Ingredient are untouched — deactivation only flips is_active,
        it never deletes or reassigns the row.

        Args:
            db: The active database session.
            actor: The Warehouse Manager or Admin performing the deactivation, used only for
                logging.
            ingredient_id: The id of the Ingredient to deactivate.

        Returns:
            The deactivated Ingredient.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        ingredient = await self._get_ingredient(db, ingredient_id)

        if not ingredient.is_active:
            return ingredient

        ingredient.is_active = False
        await db.commit()
        await db.refresh(ingredient)
        self._logger.info(
            "Ingredient deactivated by user_id={}: ingredient_id={}", actor.id, ingredient_id
        )
        return ingredient

    async def reactivate_ingredient(self, db: AsyncSession, actor: User, ingredient_id: int) -> Ingredient:
        """Reactivate a previously deactivated Ingredient, restoring its normal use.

        Mirrors UserService.reactivate_user exactly.

        Args:
            db: The active database session.
            actor: The Warehouse Manager or Admin performing the reactivation, used only for
                logging.
            ingredient_id: The id of the Ingredient to reactivate.

        Returns:
            The reactivated Ingredient.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        ingredient = await self._get_ingredient(db, ingredient_id)

        if ingredient.is_active:
            return ingredient

        ingredient.is_active = True
        await db.commit()
        await db.refresh(ingredient)
        self._logger.info(
            "Ingredient reactivated by user_id={}: ingredient_id={}", actor.id, ingredient_id
        )
        return ingredient

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
        (NFR-4). purchase/waste apply as +/-quantity; adjustment applies payload.quantity as
        already signed. current_stock is rejected cleanly (before any mutation) if the movement
        would drive it negative (AD-16 reversed): manual movements can no longer drive stock below
        zero.

        Story 4.2: broadcasts inventory.alerts_changed to warehouse_manager connections, but only
        when this movement crosses the shortage threshold in either direction (current_stock <
        min_stock_threshold flips), not on every movement. was_low is read for free from the
        Ingredient row _lock_ingredient already loaded, no extra query; is_low still costs the
        same db.refresh() this method already performs for its own return value, not a new
        round-trip added by the crossing check itself.

        Args:
            db: The active database session.
            actor: The Warehouse Manager or Admin logging the movement.
            ingredient_id: The id of the Ingredient the movement applies to.
            payload: The submitted movement type, quantity, and optional note.

        Returns:
            The newly recorded Stock Movement.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
            IngredientNotActiveError: If the Ingredient is currently deactivated (Story #3/#4).
            StockMovementWouldGoNegativeError: If this movement would drive current_stock below
                zero.
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

        if not ingredient.is_active:
            self._logger.warning(
                "Stock movement rejected by user_id={}: ingredient_id={} is deactivated",
                actor.id,
                ingredient_id,
            )
            raise IngredientNotActiveError()

        was_low = ingredient.current_stock < ingredient.min_stock_threshold

        delta = -payload.quantity if payload.movement_type == MovementType.waste else payload.quantity

        # Checked before any mutation (no rollback needed, nothing written yet): AD-16 reversed,
        # a manual movement that would drive current_stock negative is rejected cleanly rather
        # than applied in full past zero.
        if ingredient.current_stock + delta < 0:
            self._logger.warning(
                "Stock movement rejected by user_id={}: ingredient_id={} current_stock={} "
                "delta={} would go negative",
                actor.id,
                ingredient_id,
                ingredient.current_stock,
                delta,
            )
            raise StockMovementWouldGoNegativeError()

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

        is_low = ingredient.current_stock < ingredient.min_stock_threshold
        if was_low != is_low:
            self._logger.info(
                "Low-stock alert {} for ingredient_id={}: current_stock={} min_stock_threshold={}",
                "activated" if is_low else "cleared",
                ingredient_id,
                ingredient.current_stock,
                ingredient.min_stock_threshold,
            )
            await self._realtime_service.broadcast(
                [UserRole.warehouse_manager],
                "inventory.alerts_changed",
                {"ingredient_id": ingredient_id},
            )

        return movement

    async def apply_consumption(
        self, db: AsyncSession, ingredient_id: int, quantity: Decimal, actor_id: int, order_id: int
    ) -> bool:
        """Deduct a Recipe-driven consumption amount from an Ingredient (FR-13, Story 5.2).

        Reuses record_movement's own row-lock (trap 9) and threshold-crossing shape, but is a
        distinct method rather than a call to record_movement, for two reasons: (1)
        CreateStockMovementRequest explicitly rejects movement_type=consumption as manually
        submittable, so record_movement's payload contract cannot represent this call at all; (2)
        this deduction must be atomic with OrderService.pick_up_item's own OrderItem status UPDATE
        (AD-6, NFR-3) — record_movement commits its own transaction, which would let the stock
        deduction land even if the status UPDATE's guard later failed, or vice versa. So this
        method locks the Ingredient row and stages both the current_stock decrement and the
        StockMovement insert on the given session, but deliberately does not call db.commit() or
        broadcast anything — pick_up_item's own single commit is what makes the OrderItem
        transition and every Ingredient it touches atomic together, and a low-stock broadcast
        fired before that commit would tell a Warehouse Manager's browser to refetch data that
        was never actually committed.

        Args:
            db: The active database session, part of the caller's own transaction.
            ingredient_id: The id of the Ingredient being consumed.
            quantity: The amount to deduct (RecipeIngredient.quantity * OrderItem.quantity),
                always applied as a subtraction. Rejected before any mutation if it would drive
                current_stock negative (AD-16 reversed) — see InsufficientStockError below.
            actor_id: The id of the Cook performing the triggering pick-up, recorded as the
                StockMovement's performed_by.
            order_id: The id of the Order whose item triggered this consumption, recorded as the
                StockMovement's reference_id (FR-13's "referencing the Order").

        Returns:
            True if this deduction crosses the Ingredient's shortage threshold in either
            direction (was_low != is_low), signaling the caller should broadcast
            inventory.alerts_changed after its own commit succeeds; False otherwise.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
            InsufficientStockError: If this deduction would drive current_stock below zero. The
                caller (OrderService.pick_up_item) is responsible for rolling back any earlier
                deduction already staged on this same session in the same loop (AD-6, whole-item
                all-or-nothing) — this method itself only guards its own single deduction.
        """
        ingredient = await self._lock_ingredient(db, ingredient_id)

        was_low = ingredient.current_stock < ingredient.min_stock_threshold

        # Checked before any mutation on this Ingredient (no partial effect for this one line);
        # the caller is responsible for discarding any earlier line's already-staged deduction in
        # the same pick-up (AD-6, whole-item all-or-nothing rejection).
        if ingredient.current_stock - quantity < 0:
            self._logger.warning(
                "Consumption rejected for order_id={}: ingredient_id={} current_stock={} "
                "quantity={} would go negative",
                order_id,
                ingredient_id,
                ingredient.current_stock,
                quantity,
            )
            raise InsufficientStockError()

        ingredient.current_stock = ingredient.current_stock - quantity

        movement = StockMovement(
            ingredient_id=ingredient_id,
            movement_type=MovementType.consumption,
            quantity_change=-quantity,
            reference_id=order_id,
            performed_by=actor_id,
        )
        db.add(movement)

        is_low = ingredient.current_stock < ingredient.min_stock_threshold
        return was_low != is_low

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
