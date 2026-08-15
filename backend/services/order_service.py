from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import Order, RestaurantTable, TableStatus, User
from exceptions import TableNotAvailableError, TableNotFoundError


class OrderService:
    """Opens Tables into new Orders.

    Config-free, so it is registered as a container-level Factory with only
    the logger injected, matching TableService's shape.
    """

    def __init__(self, logger: Any) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
        """
        self._logger = logger

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
