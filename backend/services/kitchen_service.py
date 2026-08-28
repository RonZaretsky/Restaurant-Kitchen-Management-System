from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import KitchenItemResponse, Order, OrderItem, OrderItemStatus, OrderStatus
from services.inventory_service import InventoryService


class KitchenService:
    """Reads the Kitchen Display's live board (Story 5.1).

    Config-free aside from the inventory_service collaborator, so it is registered as a
    container-level Factory with the logger and inventory_service injected. Read-only itself: this
    service never writes, and holds no realtime_service collaborator, since it never broadcasts
    anything itself — the one event the Kitchen Display listens for (order.item_added) is
    OrderService's own broadcast, just widened to include Cook (Story 5.1's Scope note).
    inventory_service is used to compute each pending item's live max_preparable_quantity (this
    batch), reusing InventoryService.max_preparable_quantities rather than duplicating its
    recipe/stock join here.
    """

    def __init__(self, logger: Any, inventory_service: InventoryService) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
            inventory_service: Injected service used to compute each pending item's live
                max-preparable-quantity (this batch's insufficient-stock warning).
        """
        self._logger = logger
        self._inventory_service = inventory_service

    async def list_active_items(self, db: AsyncSession) -> Sequence[KitchenItemResponse]:
        """List every non-cancelled, non-rejected Order Item, grouped implicitly by Table via sort
        order.

        No actor argument: a plain unfiltered read has nothing to reject and nothing worth
        auditing, permissions are Role-level only (matches list_ingredients/list_items). The one
        join in this codebase's services/ layer this story explicitly justifies: OrderItem has no
        table_id of its own, only order_id, and the Kitchen Display's whole point is grouping by
        Table, so Order.table_id is joined in rather than resolved via a second per-item request.

        Filter scope: OrderItem.status not in (cancelled, rejected), plus (Story 5.4) Order.status
        not in (served, closed) — a served/closed Order's items keep their own ready status and
        would otherwise leak onto this board forever, now that Story 5.4 makes served/closed
        Orders reachable for the first time. rejected (this batch) is excluded the same way
        cancelled always has been: a rejected item is done as far as the kitchen board is
        concerned, its message lives on the Waiter's own order view instead.

        max_preparable_quantity is computed live, batched over every distinct Dish among this
        call's pending items only (`InventoryService.max_preparable_quantities`, one query, not
        one per item) — a non-pending item already reserved or completed its own stock, so its
        field is simply its own quantity (never flags a false shortage on a row with no
        pick-up/reject action to take).

        Args:
            db: The active database session.

        Returns:
            Every non-cancelled, non-rejected Order Item belonging to a not-yet-served Order,
            ordered by table_id then item id (oldest-added first within a table), each carrying
            its own resolved table_id and live max_preparable_quantity.
        """
        result = await db.execute(
            select(OrderItem, Order.table_id)
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                OrderItem.status.not_in([OrderItemStatus.cancelled, OrderItemStatus.rejected]),
                Order.status.not_in([OrderStatus.served, OrderStatus.closed]),
            )
            .order_by(Order.table_id, OrderItem.id)
        )
        rows = result.all()

        pending_dish_ids = {item.dish_id for item, _ in rows if item.status == OrderItemStatus.pending}
        max_preparable_by_dish = await self._inventory_service.max_preparable_quantities(db, list(pending_dish_ids))

        return [
            KitchenItemResponse.from_item(
                item,
                table_id,
                max_preparable_by_dish.get(item.dish_id, 0) if item.status == OrderItemStatus.pending else item.quantity,
            )
            for item, table_id in rows
        ]
