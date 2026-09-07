from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import (
    CreateTableRequest,
    RestaurantTable,
    TableStatus,
    UpdateTableRequest,
    User,
)
from exceptions import DuplicateTableNumberError, TableInUseError, TableNotFoundError


class TableService:
    """Creates and manages Restaurant Tables.

    Config-free, so it is registered as a container-level Factory with only
    the logger injected, matching MenuService's shape.
    """

    def __init__(self, logger: Any) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
        """
        self._logger = logger

    async def list_tables(self, db: AsyncSession) -> Sequence[RestaurantTable]:
        """List every Restaurant Table.

        No actor argument: a plain unfiltered read has nothing to reject and
        nothing worth auditing, permissions are Role-level only.

        Args:
            db: The active database session.

        Returns:
            Every RestaurantTable row, in id order.
        """
        result = await db.execute(select(RestaurantTable).order_by(RestaurantTable.id))
        return result.scalars().all()

    async def get_table(self, db: AsyncSession, actor: User, table_id: int) -> RestaurantTable:
        """Fetch a single Restaurant Table by id.

        Every by-id lookup funnels through here, mirroring MenuService.get_dish.

        Args:
            db: The active database session.
            actor: The Admin performing the lookup, used only for logging.
            table_id: The id of the Table to fetch.

        Returns:
            The matching RestaurantTable.

        Raises:
            TableNotFoundError: If no Table matches table_id.
        """
        table = await db.get(RestaurantTable, table_id)
        if table is None:
            self._logger.warning(
                "Admin action rejected for user_id={}: no table with table_id={}",
                actor.id,
                table_id,
            )
            raise TableNotFoundError()
        return table

    async def create_table(
        self, db: AsyncSession, actor: User, payload: CreateTableRequest
    ) -> RestaurantTable:
        """Create a new Restaurant Table, starting available.

        Args:
            db: The active database session.
            actor: The Admin performing the creation, used only for logging.
            payload: The submitted table number and capacity.

        Returns:
            The newly created, available RestaurantTable.

        Raises:
            DuplicateTableNumberError: If table_number already exists.
        """
        existing = await db.execute(
            select(RestaurantTable).where(RestaurantTable.table_number == payload.table_number)
        )
        if existing.scalar_one_or_none() is not None:
            self._logger.warning(
                "Table creation rejected by user_id={}: table_number={} already exists",
                actor.id,
                payload.table_number,
            )
            raise DuplicateTableNumberError()

        table = RestaurantTable(
            table_number=payload.table_number,
            capacity=payload.capacity,
            status=TableStatus.available,
        )
        db.add(table)
        try:
            await db.commit()
        except IntegrityError as exc:
            # The check above loses to a concurrent create of the same number.
            # The unique constraint is the real arbiter, so translate its violation
            # into the same 409 rather than letting it surface as a 500.
            # Logging before rollback, not after: rollback() expires every object
            # bound to this session, actor included, so reading actor.id afterward
            # would trigger an implicit lazy load with no greenlet context to run
            # it in, raising an unhandled MissingGreenlet.
            self._logger.warning(
                "Table creation rejected by user_id={}: table_number={} already exists (lost the race)",
                actor.id,
                payload.table_number,
            )
            await db.rollback()
            raise DuplicateTableNumberError() from exc
        await db.refresh(table)
        self._logger.info(
            "Table created by user_id={}: table_id={} table_number={} capacity={}",
            actor.id,
            table.id,
            table.table_number,
            table.capacity,
        )
        return table

    async def update_table(
        self, db: AsyncSession, actor: User, table_id: int, payload: UpdateTableRequest
    ) -> RestaurantTable:
        """Edit a Table's number and/or capacity, only while it is available.

        The available check and the write happen in one guarded UPDATE
        (WHERE status = 'available'), never a separate read-then-write, so a
        Waiter seating the Table between the Admin loading the form and
        saving it is rejected rather than silently applied. A zero-rowcount
        result covers both an edit attempted while
        already occupied/reserved and that race; the guarded
        UPDATE cannot distinguish them, and both use the same detail.

        Args:
            db: The active database session.
            actor: The Admin performing the edit, used only for logging.
            table_id: The id of the Table to edit.
            payload: The fields to change. At least one is always set,
                enforced by UpdateTableRequest's own validation.

        Returns:
            The updated RestaurantTable.

        Raises:
            TableNotFoundError: If no Table matches table_id.
            DuplicateTableNumberError: If table_number is changing and another
                Table already uses the new value.
            TableInUseError: If the Table's status is not available at the
                moment of the write.
        """
        table = await self.get_table(db, actor, table_id)

        changed_fields: dict[str, int] = {}
        if payload.table_number is not None and payload.table_number != table.table_number:
            changed_fields["table_number"] = payload.table_number
        if payload.capacity is not None and payload.capacity != table.capacity:
            changed_fields["capacity"] = payload.capacity

        # An edit submitting the values already stored writes nothing, and the audit
        # log must not claim a change. It is still an edit attempt, though, so the
        # same rule applies: re-read the row under the same availability filter the
        # guarded UPDATE would use, and reject if the table is in use. Returning
        # early without this check reports 200 for an operation that must be
        # rejected.
        if not changed_fields:
            still_available = await db.execute(
                select(RestaurantTable.id).where(
                    RestaurantTable.id == table_id,
                    RestaurantTable.status == TableStatus.available,
                )
            )
            if still_available.scalar_one_or_none() is None:
                self._logger.warning(
                    "Table update rejected by user_id={}: table_id={} is not available",
                    actor.id,
                    table_id,
                )
                raise TableInUseError()
            return table

        if "table_number" in changed_fields:
            duplicate = await db.execute(
                select(RestaurantTable).where(
                    RestaurantTable.table_number == changed_fields["table_number"],
                    RestaurantTable.id != table_id,
                )
            )
            if duplicate.scalar_one_or_none() is not None:
                self._logger.warning(
                    "Table update rejected by user_id={}: table_id={} table_number={} already exists",
                    actor.id,
                    table_id,
                    changed_fields["table_number"],
                )
                raise DuplicateTableNumberError()

        try:
            result = await db.execute(
                update(RestaurantTable)
                .where(RestaurantTable.id == table_id, RestaurantTable.status == TableStatus.available)
                .values(**changed_fields)
            )
            if result.rowcount == 0:
                # Either the table was already occupied/reserved or a Waiter
                # seated it between this request's read and this write. The
                # guarded UPDATE cannot tell those apart, and both use one message.
                self._logger.warning(
                    "Table update rejected by user_id={}: table_id={} is not available",
                    actor.id,
                    table_id,
                )
                await db.rollback()
                raise TableInUseError()
            # Committed inside the try: a unique violation can surface at commit
            # rather than at execution, and outside this block it would escape as
            # an unhandled 500 instead of the 409 below.
            await db.commit()
        except IntegrityError as exc:
            # The duplicate check above loses to a concurrent rename to the same
            # number. Logging before rollback, not after: rollback() expires every
            # object bound to this session, and actor is one of them, so reading
            # actor.id afterward would trigger an implicit lazy-load with no
            # greenlet context to run it in (an unhandled MissingGreenlet,
            # reproduced by test).
            if "table_number" in changed_fields:
                self._logger.warning(
                    "Table update rejected by user_id={}: table_id={} table_number={} already exists (lost the race)",
                    actor.id,
                    table_id,
                    changed_fields["table_number"],
                )
            else:
                self._logger.warning(
                    "Table update failed by user_id={}: table_id={} violated a database constraint",
                    actor.id,
                    table_id,
                )
            await db.rollback()
            raise DuplicateTableNumberError() from exc

        await db.refresh(table)
        self._logger.info(
            "Table updated by user_id={}: table_id={} changed_fields={}",
            actor.id,
            table_id,
            list(changed_fields),
        )
        return table
