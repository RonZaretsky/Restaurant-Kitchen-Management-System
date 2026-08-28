from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import (
    CreateOrderItemRequest,
    Dish,
    Order,
    OrderItem,
    OrderItemResponse,
    OrderItemStatus,
    OrderResponse,
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
    InsufficientStockError,
    OrderItemNotCancellableError,
    OrderItemNotFoundError,
    OrderItemNotInPreparationError,
    OrderItemNotPendingError,
    OrderNotClosableError,
    OrderNotFoundError,
    OrderNotServableError,
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

    async def list_open_orders(self, db: AsyncSession, actor: User) -> Sequence[Order]:
        """List every currently open (non-closed) Order, across every Table (AC4).

        The first bulk Order read in this codebase — every other Order read is scoped to one
        Table (get_open_order_for_table) or one Order's items. Backs the Tables grid's need to
        know, across every occupied Table at once, which one has a ready Order (the Story 5.3
        attention-state tile treatment) without an N+1 per-tile request. No actor-based filtering
        (AD-9: permissions are Role-level only), actor is accepted only for signature symmetry
        with every other method in this service, unused otherwise.

        Args:
            db: The active database session.
            actor: The Waiter making the request.

        Returns:
            Every Order whose status is not closed, in id order.
        """
        result = await db.execute(select(Order).where(Order.status != OrderStatus.closed).order_by(Order.id))
        return result.scalars().all()

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
        updated_order, order_status_changed = await self._recompute_order_status(db, order_id)
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
        if order_status_changed:
            assert updated_order is not None  # order_status_changed is only True when it isn't
            await self._broadcast_order_status_changed(db, updated_order)
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
        silently apply it (AC4). Broadcasts order.item_status_changed to [waiter, cook] after
        commit (Story 5.5, NFR-1) — the same event/payload/recipients pick_up_item/mark_item_ready
        already use, reused here even though the item's status itself did not change, since both
        live consumers (Kitchen Display, Table/Order Detail) already treat this event generically
        as "refetch this Order's items," not as a status-specific signal.

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
        await self._realtime_service.broadcast(
            [UserRole.waiter, UserRole.cook],
            "order.item_status_changed",
            OrderItemResponse.model_validate(item).model_dump(mode="json"),
        )
        return item

    async def cancel_item(self, db: AsyncSession, actor: User, order_id: int, item_id: int) -> OrderItem:
        """Cancel a pending or in_preparation Order Item (AC2/AC3).

        Guarded on status IN ('pending', 'in_preparation') at the moment of the write (AD-6): an
        item already ready or already cancelled cannot be cancelled again. Cancelling never
        reverses a prior stock deduction (AD-11), no compensating StockMovement is inserted here
        or anywhere else; the frontend's confirm dialog for an in_preparation item is what tells
        the actor this before they commit to it (AC3, UX-DR12), the backend enforces no stock rule
        because there is none to enforce, only the state transition itself. Broadcasts
        order.item_status_changed to [waiter, cook] after commit (Story 5.5, NFR-1), unconditional
        and placed before the existing order.status_changed conditional below — the item-level
        event is the primary signal, the order-level one a secondary, conditional follow-up
        (Story 5.3's own ordering convention).

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

        updated_order, order_status_changed = await self._recompute_order_status(db, order_id)
        await db.commit()
        await db.refresh(item)
        self._logger.info(
            "Order item cancelled by user_id={}: order_id={} item_id={}",
            actor.id,
            order_id,
            item_id,
        )
        await self._realtime_service.broadcast(
            [UserRole.waiter, UserRole.cook],
            "order.item_status_changed",
            OrderItemResponse.model_validate(item).model_dump(mode="json"),
        )
        if order_status_changed:
            assert updated_order is not None  # order_status_changed is only True when it isn't
            await self._broadcast_order_status_changed(db, updated_order)
        return item

    async def pick_up_item(self, db: AsyncSession, actor: User, order_id: int, item_id: int) -> OrderItem:
        """Pick up a pending Order Item, deducting its Recipe's stock atomically (AC1, AC2, AC4, AC7, AC8).

        A single guarded UPDATE (AD-6, trap 18) moves the item from pending to in_preparation and
        records the acting Cook, in the same transaction as every Recipe Ingredient's stock
        deduction and StockMovement insert (InventoryService.apply_consumption, trap 9's row lock,
        composed here rather than duplicated). Guarding on status == pending is also what rejects
        a re-trigger on an already in_preparation/ready/cancelled item (AC2/AC5): the precondition
        simply no longer holds, regardless of what the current status actually is. Deduction is
        rejected, whole-item and all-or-nothing, if any Recipe Ingredient line would drive its
        Ingredient's current_stock negative (AD-16 reversed) — see InsufficientStockError below.
        Epic 4's existing low-stock crossing check still fires on a successful pick-up (AC7),
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
            InsufficientStockError: If any Recipe Ingredient line would drive its Ingredient's
                current_stock negative (whole-item, all-or-nothing: the guarded status UPDATE and
                every already-applied deduction from an earlier line in this same pick-up are all
                rolled back together, the item stays pending).
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
        except (IngredientNotFoundError, InsufficientStockError):
            # Explicit rollback, matching every other rejection branch in this file (trap 20):
            # the guarded status UPDATE above already ran on this session but was never committed,
            # so this discards it rather than relying on the session's own close-time behavior.
            # Also discards every already-applied deduction from an earlier RecipeIngredient line
            # in this same loop (whole-item, all-or-nothing rejection): apply_consumption stages
            # its mutation on this same session without committing, so a later line's rejection
            # rolls every earlier line's deduction back too.
            self._logger.error(
                "Order item pick-up failed for user_id={}: order_id={} item_id={} references a"
                " missing ingredient or insufficient stock",
                actor.id,
                order_id,
                item_id,
            )
            await db.rollback()
            raise

        updated_order, order_status_changed = await self._recompute_order_status(db, order_id)
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
        if order_status_changed:
            assert updated_order is not None  # order_status_changed is only True when it isn't
            await self._broadcast_order_status_changed(db, updated_order)
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

        updated_order, order_status_changed = await self._recompute_order_status(db, order_id)
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
        if order_status_changed:
            assert updated_order is not None  # order_status_changed is only True when it isn't
            await self._broadcast_order_status_changed(db, updated_order)
        return item

    async def mark_served(self, db: AsyncSession, actor: User, order_id: int) -> Order:
        """Mark a ready (or zero-item) Order served, a pure status change (AC1, AC2, FR-11).

        A guarded transition (AD-6, trap 18), unlike Story 5.3's `_recompute_order_status`: there
        is a real expected prior status to check here, not a pure recompute. The guard accepts
        both `ready` and `pending` because, per FR-12, an Order is `pending` if and only if it
        currently has zero non-cancelled Order Items — the status column already encodes that
        fact, so no separate item count is needed.

        Args:
            db: The active database session.
            actor: The Waiter marking the Order served.
            order_id: The id of the Order to mark served.

        Returns:
            The now-served Order.

        Raises:
            OrderNotFoundError: If no Order matches order_id.
            OrderNotServableError: If the Order's status is not ready or pending at the moment of
                the write (AC2).
        """
        order = await self._get_order(db, actor, order_id)

        result = await db.execute(
            update(Order)
            .where(Order.id == order_id, Order.status.in_([OrderStatus.ready, OrderStatus.pending]))
            .values(status=OrderStatus.served)
        )
        if result.rowcount == 0:
            self._logger.warning(
                "Order mark-served rejected for user_id={}: order_id={} is not ready or pending",
                actor.id,
                order_id,
            )
            await db.rollback()
            raise OrderNotServableError()

        await db.commit()
        await db.refresh(order)
        self._logger.info(
            "Order marked served by user_id={}: order_id={}",
            actor.id,
            order_id,
        )
        await self._broadcast_order_status_changed(db, order)
        return order

    async def close_order(self, db: AsyncSession, actor: User, order_id: int) -> Order:
        """Close a served Order, computing its total and freeing its Table (AC3, AC4, AC5, FR-8).

        A guarded transition (AD-6, trap 18): Order.status moves from served to closed, in the
        same transaction as computing Order.total_amount (sum of price_at_add x quantity over
        non-cancelled Order Items, AD-7) and returning the owning Table to available. All three
        writes commit together — a closed Order whose Table never reopened, or vice versa, is a
        state nothing later can recover from cleanly, the same "things that change together
        commit together" principle AD-6 already applies to pick-up's stock deduction.

        No row lock is needed for the total's aggregate read (contrast trap 27, Story 5.3): by
        the time an Order reaches served, every non-cancelled Order Item is already ready
        (mark_served's own guard only accepts ready/pending, and ready per FR-12 means every
        non-cancelled item already is), and no later action can change any Order Item's status
        once its Order is served (cancel_item only accepts pending/in_preparation items, none of
        which exist once served). The item set is frozen, so reading it here sees a value nothing
        else can be concurrently mutating.

        Args:
            db: The active database session.
            actor: The Waiter closing the Order.
            order_id: The id of the Order to close.

        Returns:
            The now-closed Order, with total_amount populated.

        Raises:
            OrderNotFoundError: If no Order matches order_id.
            OrderNotClosableError: If the Order's status is not served at the moment of the write
                (AC4).
        """
        order = await self._get_order(db, actor, order_id)

        result = await db.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == OrderStatus.served)
            .values(status=OrderStatus.closed, closed_at=func.now())
        )
        if result.rowcount == 0:
            self._logger.warning(
                "Order close rejected for user_id={}: order_id={} is not served",
                actor.id,
                order_id,
            )
            await db.rollback()
            raise OrderNotClosableError()

        items_result = await db.execute(
            select(OrderItem.price_at_add, OrderItem.quantity).where(
                OrderItem.order_id == order_id,
                OrderItem.status != OrderItemStatus.cancelled,
            )
        )
        total = sum(
            (price_at_add * quantity for price_at_add, quantity in items_result.all()),
            start=Decimal("0.00"),
        )
        order.total_amount = total

        table_result = await db.execute(
            update(RestaurantTable)
            .where(RestaurantTable.id == order.table_id, RestaurantTable.status == TableStatus.occupied)
            .values(status=TableStatus.available)
        )
        table_freed = table_result.rowcount > 0
        if not table_freed:
            self._logger.error(
                "Order close for order_id={} table_id={} did not free the table: table was not"
                " occupied",
                order_id,
                order.table_id,
            )

        await db.commit()
        await db.refresh(order)
        self._logger.info(
            "Order closed by user_id={}: order_id={} total_amount={} table_id={}",
            actor.id,
            order_id,
            order.total_amount,
            order.table_id,
        )
        await self._broadcast_order_status_changed(db, order)
        # Only broadcast the Table as freed if it genuinely was — otherwise a client would be
        # told the table is available when its DB status never actually changed (review finding).
        if table_freed:
            await self._realtime_service.broadcast(
                [UserRole.waiter],
                "table.status_changed",
                {"table_id": order.table_id, "status": TableStatus.available.value},
            )
        return order

    async def _recompute_order_status(self, db: AsyncSession, order_id: int) -> tuple[Order | None, bool]:
        """Recompute Order.status from its non-cancelled Items (FR-12).

        A pure recomputation, not a guarded transition (AD-6 does not apply): there is no expected
        prior status to check, only a value to overwrite with whatever the aggregate says right
        now, converging to the same correct answer however many times it runs *sequentially*.
        `served`/`closed` are set explicitly (a later story's territory, FR-11/FR-8) and are never
        overwritten here, forward-safe even though nothing today can ever produce a `served`/
        `closed` Order yet.

        The Order row is locked (`SELECT ... FOR UPDATE`, trap 9's row-lock idiom, the same
        pattern `InventoryService._lock_ingredient`/`MenuService._lock_dish` already use) before
        reading its sibling Items. Without this lock, two concurrent transactions each finishing a
        *different* Item of the same multi-item Order could each read the other's not-yet-committed
        Item status, each independently compute "no change" from their own narrow view, and leave
        Order.status permanently stuck wrong after both commit — the lock forces the second
        transaction's read to wait for the first's commit, so it sees the first's already-applied
        change and recomputes correctly. Always acquired after any OrderItem/Ingredient lock this
        method's callers already hold (never before), so no new lock-ordering/deadlock risk.

        Mutates the given Order's `.status` attribute in place, in the caller's own session, but
        does not commit — the caller commits this together with the OrderItem write that triggered
        the recompute, in the same transaction (mirrors AD-6's "things that change together commit
        together" principle for the stock-deduction path).

        Args:
            db: The active database session, mid-transaction.
            order_id: The Order whose status is being recomputed.

        Returns:
            A tuple of (the Order row, or None if it does not exist; whether this call changed
            Order.status). The second element is False whenever the first is None.
        """
        result = await db.execute(select(Order).where(Order.id == order_id).with_for_update())
        order = result.scalar_one_or_none()
        if order is None:
            return None, False
        if order.status not in (OrderStatus.pending, OrderStatus.in_preparation, OrderStatus.ready):
            return order, False

        items_result = await db.execute(
            select(OrderItem.status).where(
                OrderItem.order_id == order_id,
                OrderItem.status != OrderItemStatus.cancelled,
            )
        )
        statuses = items_result.scalars().all()

        if not statuses:
            new_status = OrderStatus.pending
        elif all(status == OrderItemStatus.ready for status in statuses):
            new_status = OrderStatus.ready
        else:
            new_status = OrderStatus.in_preparation

        if new_status == order.status:
            return order, False

        old_status = order.status
        order.status = new_status
        self._logger.info(
            "Order status recomputed: order_id={} status {} -> {}",
            order_id,
            old_status.value,
            new_status.value,
        )
        return order, True

    async def _broadcast_order_status_changed(self, db: AsyncSession, order: Order) -> None:
        """Refresh and broadcast an Order whose derived status just changed (AD-2, AC4).

        Called only when `_recompute_order_status` returned a True changed-flag, after the
        caller's own `db.commit()`: `db.commit()`'s default `expire_on_commit=True` leaves every
        attribute on `order` stale, so it is refreshed (resolving the expiry) before building the
        broadcast payload, the same refresh-after-commit convention every other method in this
        file already follows for its own `item`. Takes the already-loaded `Order` object directly
        from `_recompute_order_status` rather than re-fetching it by id, avoiding a second,
        redundant read of the same row every broadcast would otherwise pay for.

        Args:
            db: The active database session, just past its own commit.
            order: The Order whose status changed, as returned by `_recompute_order_status`.
        """
        await db.refresh(order)
        await self._realtime_service.broadcast(
            [UserRole.waiter],
            "order.status_changed",
            OrderResponse.model_validate(order).model_dump(mode="json"),
        )

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
