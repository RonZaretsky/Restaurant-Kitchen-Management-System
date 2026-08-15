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
    OrderStatus,
    RestaurantTable,
    TableStatus,
    User,
    UserRole,
)
from exceptions import (
    DishNotAvailableError,
    DishNotFoundError,
    OrderNotFoundError,
    TableNotAvailableError,
    TableNotFoundError,
)
from services.realtime_service import RealtimeService


class OrderService:
    """Opens Tables into new Orders.

    Config-free aside from the realtime_service collaborator, so it is
    registered as a container-level Factory with the logger and
    realtime_service injected, matching TableService's shape plus the push
    seam Story 3.3 adds. That seam is an Observer/Pub-Sub pattern: this
    service publishes table.status_changed/order.item_added events without
    knowing who, if anyone, is listening, and RealtimeService/ConnectionRegistry
    fan them out to every subscribed frontend client (AD-2).
    """

    def __init__(self, logger: Any, realtime_service: RealtimeService) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
            realtime_service: Injected service used to push live updates to
                connected Waiter terminals (AD-2, Story 3.3).
        """
        self._logger = logger
        self._realtime_service = realtime_service

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
            [UserRole.waiter],
            "order.item_added",
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
