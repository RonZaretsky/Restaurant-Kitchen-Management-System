from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import (
    CreateOrderItemRequest,
    Dish,
    Order,
    OrderItem,
    OrderItemResponse,
    OrderItemStatus,
    OrderStatus,
    RecipeIngredient,
    RestaurantTable,
    TableStatus,
    UpdateOrderItemRequest,
    User,
    UserRole,
)
from exceptions import (
    DishNotAvailableError,
    DishNotFoundError,
    IngredientNotFoundError,
    OrderItemNotCancellableError,
    OrderItemNotFoundError,
    OrderItemNotInPreparationError,
    OrderItemNotPendingError,
    OrderNotFoundError,
    TableNotAvailableError,
    TableNotFoundError,
)
from services.inventory_service import InventoryService
from services.realtime_service import RealtimeService


class OrderService:
    """Opens Tables into new Orders.

    Config-free aside from the realtime_service/inventory_service collaborators, so it is
    registered as a container-level Factory with the logger, realtime_service, and
    inventory_service injected, matching TableService's shape plus the push seam Story 3.3 adds
    and the stock-deduction seam Story 5.2 adds. The realtime_service seam is an Observer/Pub-Sub
    pattern: this service publishes table.status_changed/order.item_added/
    order.item_status_changed events without knowing who, if anyone, is listening, and
    RealtimeService/ConnectionRegistry fan them out to every subscribed frontend client (AD-2).
    inventory_service is used by pick_up_item to atomically deduct Recipe-driven stock
    consumption in the same transaction as the OrderItem status transition (AD-6, NFR-3),
    reusing InventoryService.apply_consumption rather than duplicating its row-lock/
    threshold-crossing logic here.
    """

    def __init__(self, logger: Any, realtime_service: RealtimeService, inventory_service: InventoryService) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
            realtime_service: Injected service used to push live updates to
                connected Waiter/Cook terminals (AD-2, Story 3.3/5.2).
            inventory_service: Injected service used to atomically deduct
                Recipe-driven stock consumption when an Order Item is picked
                up (FR-13, Story 5.2).
        """
        self._logger = logger
        self._realtime_service = realtime_service
        self._inventory_service = inventory_service

    async def open_table(self, db: AsyncSession, actor: User, table_id: int) -> Order:
        """Mark an available Table occupied and start a new Order on it (AC1).

        The Table-status check and the write happen in one guarded UPDATE
        (WHERE status = 'available'), never a separate read-then-write, so two
        Waiters opening the same Table at once cannot both succeed (AD-6
        pattern, the same shape TableService.update_table already uses). A
        zero-rowcount result means the Table was already occupied/reserved,
        or lost exactly that race (AC2); the guarded UPDATE cannot
        distinguish the two, and both raise the same error. The Order is only
        inserted, and both writes only committed together, once that UPDATE
        succeeds: a Table left occupied with no Order to show for it (or vice
        versa) is a state no later story can recover from cleanly.

        Args:
            db: The active database session.
            actor: The Waiter opening the Table.
            table_id: The id of the Table to open.

        Returns:
            The newly created, pending Order.

        Raises:
            TableNotFoundError: If no Table matches table_id.
            TableNotAvailableError: If the Table's status is not available at
                the moment of the write.
        """
        await self._get_table(db, actor, table_id)

        result = await db.execute(
            update(RestaurantTable)
            .where(RestaurantTable.id == table_id, RestaurantTable.status == TableStatus.available)
            .values(status=TableStatus.occupied)
        )
        if result.rowcount == 0:
            self._logger.warning(
                "Order open rejected for user_id={}: table_id={} is not available",
                actor.id,
                table_id,
            )
            await db.rollback()
            raise TableNotAvailableError()

        order = Order(table_id=table_id, waiter_id=actor.id)
        db.add(order)
        await db.commit()
        await db.refresh(order)
        self._logger.info(
            "Table opened by user_id={}: table_id={} order_id={}",
            actor.id,
            table_id,
            order.id,
        )
        # A plain dict, not a Pydantic response model like order.item_added's
        # payload below: TablesPage.tsx's subscriber only reads this as a
        # refetch signal and never parses table_id/status out of it (it calls
        # useTables() again for the real data), so there is no consumer that
        # needs a full TableResponse, and building one here would cost an
        # extra SELECT of the just-updated row purely to satisfy a payload
        # shape nothing reads.
        await self._realtime_service.broadcast(
            [UserRole.waiter],
            "table.status_changed",
            {"table_id": table_id, "status": TableStatus.occupied.value},
        )
        return order

    async def get_open_order_for_table(self, db: AsyncSession, actor: User, table_id: int) -> Order:
        """Fetch the Order currently open on a Table.

        "Open" means not yet closed, FR-8's close action (a later story) is the only thing that
        can ever change that. Only one non-closed Order can exist per Table at a time, opening a
        Table requires it to be available first (Story 3.1's AC2), so this is a single filtered
        SELECT, not a "most recent of several" query.

        Args:
            db: The active database session.
            actor: The Waiter making the request, used only for logging.
            table_id: The id of the Table whose open Order is being fetched.

        Returns:
            The matching, currently-open Order.

        Raises:
            TableNotFoundError: If no Table matches table_id.
            OrderNotFoundError: If the Table exists but has no currently open Order.
        """
        table = await db.get(RestaurantTable, table_id)
        if table is None:
            self._logger.warning(
                "Order lookup rejected for user_id={}: no table with table_id={}",
                actor.id,
                table_id,
            )
            raise TableNotFoundError()

        result = await db.execute(
            select(Order).where(Order.table_id == table_id, Order.status != OrderStatus.closed)
        )
        order = result.scalar_one_or_none()
        if order is None:
            self._logger.warning(
                "Order lookup rejected for user_id={}: table_id={} has no open order",
                actor.id,
                table_id,
            )
            raise OrderNotFoundError()
        return order

    async def list_items(self, db: AsyncSession, actor: User, order_id: int) -> Sequence[OrderItem]:
        """List every Order Item on an Order, in id order.

        A plain SELECT against current state every call, never cached, mirroring
        MenuService.list_recipe_ingredients.

        Args:
            db: The active database session.
            actor: The Waiter making the request, used only for logging.
            order_id: The id of the Order whose items are being listed.

        Returns:
            Every OrderItem row for this Order.

        Raises:
            OrderNotFoundError: If no Order matches order_id.
        """
        await self._get_order(db, actor, order_id)
        result = await db.execute(select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id))
        return result.scalars().all()

    async def add_item(
        self, db: AsyncSession, actor: User, order_id: int, payload: CreateOrderItemRequest
    ) -> OrderItem:
        """Add a new Order Item to an Order, at status pending (AC1).

        No guarded/atomic UPDATE is needed here: AD-6 governs transitioning an existing OrderItem's
        status, not this plain insert of a new one. No row lock is needed either, this mirrors
        MenuService.add_recipe_ingredient's plain check-then-insert shape.

        Args:
            db: The active database session.
            actor: The Waiter adding the item.
            order_id: The id of the Order the item is being added to.
            payload: The submitted dish, quantity, and optional note.

        Returns:
            The newly created Order Item, price_at_add copied from the Dish's
            current price (AD-7).

        Raises:
            OrderNotFoundError: If no Order matches order_id.
            DishNotFoundError: If no Dish matches payload.dish_id.
            DishNotAvailableError: If the Dish is currently unavailable.
        """
        await self._get_order(db, actor, order_id)

        dish = await db.get(Dish, payload.dish_id)
        if dish is None:
            self._logger.warning(
                "Order item addition rejected for user_id={}: order_id={} no dish with dish_id={}",
                actor.id,
                order_id,
                payload.dish_id,
            )
            raise DishNotFoundError()

        if not dish.is_available:
            self._logger.warning(
                "Order item addition rejected for user_id={}: order_id={} dish_id={} is unavailable",
                actor.id,
                order_id,
                payload.dish_id,
            )
            raise DishNotAvailableError()

        item = OrderItem(
            order_id=order_id,
            dish_id=payload.dish_id,
            quantity=payload.quantity,
            notes=payload.notes,
            price_at_add=dish.price,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        self._logger.info(
            "Order item added by user_id={}: order_id={} item_id={} dish_id={} quantity={}",
            actor.id,
            order_id,
            item.id,
            item.dish_id,
            item.quantity,
        )
        await self._realtime_service.broadcast(
            [UserRole.waiter, UserRole.cook],
            "order.item_added",
            OrderItemResponse.model_validate(item).model_dump(mode="json"),
        )
        return item

    async def edit_item(
        self,
        db: AsyncSession,
        actor: User,
        order_id: int,
        item_id: int,
        payload: UpdateOrderItemRequest,
    ) -> OrderItem:
        """Edit a pending Order Item's quantity and/or note (AC1).

        Guarded on status = 'pending' at the moment of the write (AD-6): an item that has already
        moved to in_preparation between this request's read and write must reject the edit, not
        silently apply it (AC4). No live broadcast, this story's own ACs never say "live" for
        edit/cancel the way Story 3.3's did for open/add.

        Args:
            db: The active database session.
            actor: The Waiter editing the item.
            order_id: The id of the Order the item belongs to.
            item_id: The id of the Order Item to edit.
            payload: The submitted quantity and/or note.

        Returns:
            The updated Order Item.

        Raises:
            OrderItemNotFoundError: If no Order Item matches item_id on order_id.
            OrderItemNotPendingError: If the item's status is not pending at the moment of the write.
        """
        item = await self._get_item(db, actor, order_id, item_id)

        result = await db.execute(
            update(OrderItem)
            .where(OrderItem.id == item_id, OrderItem.status == OrderItemStatus.pending)
            .values(quantity=payload.quantity, notes=payload.notes)
        )
        if result.rowcount == 0:
            self._logger.warning(
                "Order item edit rejected for user_id={}: order_id={} item_id={} is not pending",
                actor.id,
                order_id,
                item_id,
            )
            await db.rollback()
            raise OrderItemNotPendingError()

        await db.commit()
        await db.refresh(item)
        self._logger.info(
            "Order item edited by user_id={}: order_id={} item_id={} quantity={}",
            actor.id,
            order_id,
            item_id,
            payload.quantity,
        )
        return item

    async def cancel_item(self, db: AsyncSession, actor: User, order_id: int, item_id: int) -> OrderItem:
        """Cancel a pending or in_preparation Order Item (AC2/AC3).

        Guarded on status IN ('pending', 'in_preparation') at the moment of the write (AD-6): an
        item already ready or already cancelled cannot be cancelled again. Cancelling never
        reverses a prior stock deduction (AD-11), no compensating StockMovement is inserted here
        or anywhere else; the frontend's confirm dialog for an in_preparation item is what tells
        the actor this before they commit to it (AC3, UX-DR12), the backend enforces no stock rule
        because there is none to enforce, only the state transition itself.

        Args:
            db: The active database session.
            actor: The Waiter, Cook, or Admin cancelling the item.
            order_id: The id of the Order the item belongs to.
            item_id: The id of the Order Item to cancel.

        Returns:
            The now-cancelled Order Item.

        Raises:
            OrderItemNotFoundError: If no Order Item matches item_id on order_id.
            OrderItemNotCancellableError: If the item's status is not pending or in_preparation at
                the moment of the write.
        """
        item = await self._get_item(db, actor, order_id, item_id)

        result = await db.execute(
            update(OrderItem)
            .where(
                OrderItem.id == item_id,
                OrderItem.status.in_([OrderItemStatus.pending, OrderItemStatus.in_preparation]),
            )
            .values(status=OrderItemStatus.cancelled)
        )
        if result.rowcount == 0:
            self._logger.warning(
                "Order item cancel rejected for user_id={}: order_id={} item_id={} is not cancellable",
                actor.id,
                order_id,
                item_id,
            )
            await db.rollback()
            raise OrderItemNotCancellableError()

        await db.commit()
        await db.refresh(item)
        self._logger.info(
            "Order item cancelled by user_id={}: order_id={} item_id={}",
            actor.id,
            order_id,
            item_id,
        )
        return item

    async def pick_up_item(self, db: AsyncSession, actor: User, order_id: int, item_id: int) -> OrderItem:
        """Pick up a pending Order Item, deducting its Recipe's stock atomically (AC1, AC2, AC4, AC7, AC8).

        A single guarded UPDATE (AD-6, trap 18) moves the item from pending to in_preparation and
        records the acting Cook, in the same transaction as every Recipe Ingredient's stock
        deduction and StockMovement insert (InventoryService.apply_consumption, trap 9's row lock,
        composed here rather than duplicated). Guarding on status == pending is also what rejects
        a re-trigger on an already in_preparation/ready/cancelled item (AC2/AC5): the precondition
        simply no longer holds, regardless of what the current status actually is. Deduction never
        floor-caps at zero (AD-16, AC7) — a Recipe requiring more than is currently in stock still
        deducts in full, and Epic 4's existing low-stock crossing check still fires for it (AC7),
        broadcast only after this transaction's own commit succeeds.

        Args:
            db: The active database session.
            actor: The Cook picking up the item.
            order_id: The id of the Order the item belongs to.
            item_id: The id of the Order Item to pick up.

        Returns:
            The now in_preparation Order Item.

        Raises:
            OrderItemNotFoundError: If no Order Item matches item_id on order_id.
            OrderItemNotPendingError: If the item's status is not pending at the moment of the write.
        """
        item = await self._get_item(db, actor, order_id, item_id)

        result = await db.execute(
            update(OrderItem)
            .where(OrderItem.id == item_id, OrderItem.status == OrderItemStatus.pending)
            .values(status=OrderItemStatus.in_preparation, cook_id=actor.id)
        )
        if result.rowcount == 0:
            self._logger.warning(
                "Order item pick-up rejected for user_id={}: order_id={} item_id={} is not pending",
                actor.id,
                order_id,
                item_id,
            )
            await db.rollback()
            raise OrderItemNotPendingError()

        # Refreshed here, not just relied on from _get_item's earlier read: the guarded UPDATE
        # above only just succeeded, meaning the item was still pending an instant ago and a
        # concurrent edit_item (also guarded on status == pending) could have committed a new
        # quantity in the narrow window between _get_item's read and this UPDATE. Now that our own
        # UPDATE has moved status to in_preparation, no further edit_item call can land (its own
        # guard requires status == pending), so this refresh is the last point a quantity change
        # could still be pending, and the one this deduction must use (review finding, Story 5.2).
        await db.refresh(item)

        recipe_result = await db.execute(
            select(RecipeIngredient)
            .where(RecipeIngredient.dish_id == item.dish_id)
            .order_by(RecipeIngredient.ingredient_id)
        )
        recipe_ingredients = recipe_result.scalars().all()

        crossed_ingredient_ids: list[int] = []
        try:
            for recipe_ingredient in recipe_ingredients:
                crossed = await self._inventory_service.apply_consumption(
                    db,
                    recipe_ingredient.ingredient_id,
                    recipe_ingredient.quantity * item.quantity,
                    actor.id,
                    order_id,
                )
                if crossed:
                    crossed_ingredient_ids.append(recipe_ingredient.ingredient_id)
        except IngredientNotFoundError:
            # Explicit rollback, matching every other rejection branch in this file (trap 20):
            # the guarded status UPDATE above already ran on this session but was never committed,
            # so this discards it rather than relying on the session's own close-time behavior.
            self._logger.error(
                "Order item pick-up failed for user_id={}: order_id={} item_id={} references a"
                " missing ingredient",
                actor.id,
                order_id,
                item_id,
            )
            await db.rollback()
            raise

        await db.commit()
        await db.refresh(item)
        self._logger.info(
            "Order item picked up by user_id={}: order_id={} item_id={} dish_id={} ingredients_deducted={}",
            actor.id,
            order_id,
            item_id,
            item.dish_id,
            len(recipe_ingredients),
        )
        await self._realtime_service.broadcast(
            [UserRole.waiter, UserRole.cook],
            "order.item_status_changed",
            OrderItemResponse.model_validate(item).model_dump(mode="json"),
        )
        for ingredient_id in crossed_ingredient_ids:
            self._logger.info(
                "Low-stock alert triggered by consumption: ingredient_id={} order_id={} item_id={}",
                ingredient_id,
                order_id,
                item_id,
            )
            await self._realtime_service.broadcast(
                [UserRole.warehouse_manager],
                "inventory.alerts_changed",
                {"ingredient_id": ingredient_id},
            )
        return item

    async def mark_item_ready(self, db: AsyncSession, actor: User, order_id: int, item_id: int) -> OrderItem:
        """Mark an in_preparation Order Item ready, a pure status change (AC3, AC5, AC6, AC8).

        Guarded on status == in_preparation (AD-6, trap 18): rejects a pending item skipping ahead
        (AC4), an already-ready item re-triggering the transition, and any reverse transition
        (AC5). Does not reassign cook_id — the Cook recorded is whoever picked the item up, marking
        it ready never overwrites that attribution, since it is for audit only, not an access lock
        (AC6): any active Cook may call this regardless of whose cook_id is already set, including
        finishing an item a since-deactivated Cook picked up. No stock movement of any kind (AC3).

        Args:
            db: The active database session.
            actor: The Cook marking the item ready (may differ from the Cook who picked it up).
            order_id: The id of the Order the item belongs to.
            item_id: The id of the Order Item to mark ready.

        Returns:
            The now ready Order Item.

        Raises:
            OrderItemNotFoundError: If no Order Item matches item_id on order_id.
            OrderItemNotInPreparationError: If the item's status is not in_preparation at the
                moment of the write.
        """
        item = await self._get_item(db, actor, order_id, item_id)

        result = await db.execute(
            update(OrderItem)
            .where(OrderItem.id == item_id, OrderItem.status == OrderItemStatus.in_preparation)
            .values(status=OrderItemStatus.ready)
        )
        if result.rowcount == 0:
            self._logger.warning(
                "Order item mark-ready rejected for user_id={}: order_id={} item_id={} is not in_preparation",
                actor.id,
                order_id,
                item_id,
            )
            await db.rollback()
            raise OrderItemNotInPreparationError()

        await db.commit()
        await db.refresh(item)
        self._logger.info(
            "Order item marked ready by user_id={}: order_id={} item_id={}",
            actor.id,
            order_id,
            item_id,
        )
        await self._realtime_service.broadcast(
            [UserRole.waiter, UserRole.cook],
            "order.item_status_changed",
            OrderItemResponse.model_validate(item).model_dump(mode="json"),
        )
        return item

    async def _get_order(self, db: AsyncSession, actor: User, order_id: int) -> Order:
        """Fetch a single Order by id, or raise if it does not exist.

        Args:
            db: The active database session.
            actor: The Waiter performing the action, used only for logging.
            order_id: The id to look up.

        Returns:
            The matching Order.

        Raises:
            OrderNotFoundError: If no Order matches order_id.
        """
        order = await db.get(Order, order_id)
        if order is None:
            self._logger.warning(
                "Order action rejected for user_id={}: no order with order_id={}",
                actor.id,
                order_id,
            )
            raise OrderNotFoundError()
        return order

    async def _get_item(self, db: AsyncSession, actor: User, order_id: int, item_id: int) -> OrderItem:
        """Fetch a single Order Item by id, scoped to the given Order, or raise if either check fails.

        The first `_get_*` seam in this service with two ids to check, not one: an item_id that
        exists but belongs to a *different* Order must 404 the same as a missing item_id, never
        silently operate on the wrong Order's item just because the numeric id happened to match.

        Args:
            db: The active database session.
            actor: The Waiter, Cook, or Admin performing the action, used only for logging.
            order_id: The id of the Order the item is expected to belong to.
            item_id: The id of the Order Item to fetch.

        Returns:
            The matching Order Item.

        Raises:
            OrderItemNotFoundError: If no Order Item matches item_id, or it belongs to a different Order.
        """
        item = await db.get(OrderItem, item_id)
        if item is None or item.order_id != order_id:
            self._logger.warning(
                "Order item action rejected for user_id={}: no item_id={} on order_id={}",
                actor.id,
                item_id,
                order_id,
            )
            raise OrderItemNotFoundError()
        return item

    async def _get_table(self, db: AsyncSession, actor: User, table_id: int) -> RestaurantTable:
        """Fetch a single Restaurant Table by id, the open's read step.

        A separate seam (rather than inlined into open_table) so a test can
        monkeypatch just this step to land a second, competing write strictly
        between this read and open_table's own guarded UPDATE, matching
        TableService.get_table's own role in the update_table race test.

        Args:
            db: The active database session.
            actor: The Waiter opening the Table, used only for logging.
            table_id: The id of the Table to fetch.

        Returns:
            The matching RestaurantTable.

        Raises:
            TableNotFoundError: If no Table matches table_id.
        """
        table = await db.get(RestaurantTable, table_id)
        if table is None:
            self._logger.warning(
                "Order open rejected for user_id={}: no table with table_id={}",
                actor.id,
                table_id,
            )
            raise TableNotFoundError()
        return table
