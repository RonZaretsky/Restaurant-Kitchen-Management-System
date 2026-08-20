from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import KitchenItemResponse, Order, OrderItem, OrderItemStatus, OrderStatus


class KitchenService:
    """Reads the Kitchen Display's live board (Story 5.1).

    Config-free, so it is registered as a container-level Factory with only the logger injected,
    matching InventoryService's pre-Story-4.2 shape. Read-only: this service never writes, and
    holds no realtime_service collaborator, since it never broadcasts anything itself — the one
    event the Kitchen Display listens for (order.item_added) is OrderService's own broadcast,
    just widened to include Cook (Story 5.1's Scope note).
    """

    def __init__(self, logger: Any) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
        """
        self._logger = logger

    async def list_active_items(self, db: AsyncSession) -> Sequence[KitchenItemResponse]:
        """List every non-cancelled Order Item, grouped implicitly by Table via sort order.

        No actor argument: a plain unfiltered read has nothing to reject and nothing worth
        auditing, permissions are Role-level only (matches list_ingredients/list_items). The one
        join in this codebase's services/ layer this story explicitly justifies: OrderItem has no
        table_id of its own, only order_id, and the Kitchen Display's whole point is grouping by
        Table, so Order.table_id is joined in rather than resolved via a second per-item request.

        Filter scope: OrderItem.status != cancelled, plus (Story 5.4) Order.status not in (served,
        closed) — a served/closed Order's items keep their own ready status and would otherwise
        leak onto this board forever, now that Story 5.4 makes served/closed Orders reachable for
        the first time.

        Args:
            db: The active database session.

        Returns:
            Every non-cancelled Order Item belonging to a not-yet-served Order, ordered by
            table_id then item id (oldest-added first within a table), each carrying its own
            resolved table_id.
        """
        result = await db.execute(
            select(OrderItem, Order.table_id)
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                OrderItem.status != OrderItemStatus.cancelled,
                Order.status.not_in([OrderStatus.served, OrderStatus.closed]),
            )
            .order_by(Order.table_id, OrderItem.id)
        )
        return [KitchenItemResponse.from_item(item, table_id) for item, table_id in result.all()]
