from collections.abc import Sequence
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import (
    CreateOrderItemRequest,
    Order,
    OrderItem,
    OrderItemResponse,
    OrderResponse,
    UpdateOrderItemRequest,
    User,
    UserRole,
)
from data_models.menu import _INT4_MAX
from services.order_service import OrderService

router = APIRouter(prefix="/api/orders", tags=["orders"])

# Opening a table into an Order is Waiter-only (FR-4). Unlike every prior
# domain router (Admin-only, or Admin plus one other Role), this is the first
# route scoped to exactly one non-Admin Role with no Admin fallback.
OrdersDep = Annotated[User, Depends(require_role(UserRole.waiter))]

# Cancel is the one route in this file NOT waiter-only (FR-7): a Cook or Admin
# can also cancel, though neither role has a screen that reaches this endpoint
# yet (Epic 5 builds Cook's Kitchen Display). Edit stays on the existing
# waiter-only OrdersDep, unchanged. The first three-Role require_role call in
# the project; require_role already supports any number of Roles (trap 8), no
# change needed to it.
OrderItemCancelDep = Annotated[User, Depends(require_role(UserRole.waiter, UserRole.cook, UserRole.admin))]

# Pick-up and mark-ready are Cook-only (plus Admin), unlike every other route in this file
# (Waiter-scoped, or Waiter/Cook/Admin for cancel): only a Cook progresses an Order Item through
# the kitchen, matching KitchenReadDep's own (cook, admin) shape in api/kitchen.py.
OrderItemProgressDep = Annotated[User, Depends(require_role(UserRole.cook, UserRole.admin))]

# Path ids need the same int4 upper bound their request-body counterparts carry
# (trap 16), matching api/tables.py's own TableIdPath.
TableIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]
OrderIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]
ItemIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]

_ERROR_DESCRIPTIONS = {
    401: "No valid session cookie was supplied",
    403: "Authenticated, but the caller's Role is not waiter",
    404: "No matching Table was found",
    409: "The Table is not currently available",
}

_GET_ORDER_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: _ERROR_DESCRIPTIONS[403],
    404: "No matching Table was found, or the Table has no Order currently open",
}

_ITEM_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: _ERROR_DESCRIPTIONS[403],
    # Both causes, not just the Order one: add_order_item raises
    # DishNotFoundError for an unknown dish_id as well.
    404: "No matching Order or Dish was found",
    409: "The Dish is currently unavailable",
}

_EDIT_ITEM_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: _ERROR_DESCRIPTIONS[403],
    404: "No matching Order or Order Item was found",
    409: "The item is not pending",
}

_CANCEL_ITEM_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: "Authenticated, but the caller's Role is not waiter, cook, or admin",
    404: "No matching Order or Order Item was found",
    409: "The item is not pending or in_preparation",
}

_PICK_UP_ITEM_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: "Authenticated, but the caller's Role is not cook or admin",
    404: "No matching Order or Order Item was found, or the item's Dish recipe references an ingredient that no longer exists",
    409: "The item is not pending",
}

_MARK_READY_ITEM_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: "Authenticated, but the caller's Role is not cook or admin",
    404: "No matching Order or Order Item was found",
    409: "The item is not in_preparation",
}


@router.post(
    "/tables/{table_id}/open",
    response_model=OrderResponse,
    status_code=201,
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def open_table(
    table_id: TableIdPath,
    actor: OrdersDep,
    db: SessionDep,
    order_service: OrderService = Depends(Provide[Container.order_service]),
) -> Order:
    """Mark an available Table occupied and start a new Order on it (AC1).

    Args:
        table_id: The id of the Table to open.
        actor: The authenticated Waiter making the request.
        db: The active database session.
        order_service: Injected service handling the open.

    Returns:
        The newly created, pending Order.

    Raises:
        TableNotFoundError: Propagated from order_service, handled globally
            as a 404, if no Table matches table_id.
        TableNotAvailableError: Propagated from order_service, handled
            globally as a 409, if the Table's status is not available at the
            moment of the write.
    """
    return await order_service.open_table(db, actor, table_id)


@router.get(
    "/tables/{table_id}",
    response_model=OrderResponse,
    responses=error_responses(_GET_ORDER_ERROR_DESCRIPTIONS, 401, 403, 404),
)
@inject
async def get_order_for_table(
    table_id: TableIdPath,
    actor: OrdersDep,
    db: SessionDep,
    order_service: OrderService = Depends(Provide[Container.order_service]),
) -> Order:
    """Fetch the Order currently open on a Table.

    Args:
        table_id: The id of the Table whose open Order is being fetched.
        actor: The authenticated Waiter making the request.
        db: The active database session.
        order_service: Injected service handling the lookup.

    Returns:
        The matching, currently-open Order.

    Raises:
        TableNotFoundError: Propagated from order_service, handled globally
            as a 404, if no Table matches table_id.
        OrderNotFoundError: Propagated from order_service, handled globally
            as a 404, if the Table has no currently open Order.
    """
    return await order_service.get_open_order_for_table(db, actor, table_id)


@router.get(
    "/{order_id}/items",
    response_model=list[OrderItemResponse],
    responses=error_responses(_ITEM_ERROR_DESCRIPTIONS, 401, 403, 404),
)
@inject
async def list_order_items(
    order_id: OrderIdPath,
    actor: OrdersDep,
    db: SessionDep,
    order_service: OrderService = Depends(Provide[Container.order_service]),
) -> Sequence[OrderItem]:
    """List every Order Item on an Order, in id order (AC3).

    Args:
        order_id: The id of the Order whose items are being listed.
        actor: The authenticated Waiter making the request.
        db: The active database session.
        order_service: Injected service handling the lookup.

    Returns:
        Every Order Item on this Order.

    Raises:
        OrderNotFoundError: Propagated from order_service, handled globally
            as a 404, if no Order matches order_id.
    """
    return await order_service.list_items(db, actor, order_id)


@router.post(
    "/{order_id}/items",
    response_model=OrderItemResponse,
    status_code=201,
    responses=error_responses(_ITEM_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def add_order_item(
    order_id: OrderIdPath,
    payload: CreateOrderItemRequest,
    actor: OrdersDep,
    db: SessionDep,
    order_service: OrderService = Depends(Provide[Container.order_service]),
) -> OrderItem:
    """Add a new Order Item to an Order, at status pending (AC1).

    Args:
        order_id: The id of the Order the item is being added to.
        payload: The submitted dish, quantity, and optional note.
        actor: The authenticated Waiter making the request.
        db: The active database session.
        order_service: Injected service handling the addition.

    Returns:
        The newly created Order Item.

    Raises:
        OrderNotFoundError: Propagated from order_service, handled globally
            as a 404, if no Order matches order_id.
        DishNotFoundError: Propagated from order_service, handled globally
            as a 404, if no Dish matches payload.dish_id.
        DishNotAvailableError: Propagated from order_service, handled
            globally as a 409, if the Dish is currently unavailable (AC2).
    """
    return await order_service.add_item(db, actor, order_id, payload)


@router.patch(
    "/{order_id}/items/{item_id}",
    response_model=OrderItemResponse,
    responses=error_responses(_EDIT_ITEM_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def edit_order_item(
    order_id: OrderIdPath,
    item_id: ItemIdPath,
    payload: UpdateOrderItemRequest,
    actor: OrdersDep,
    db: SessionDep,
    order_service: OrderService = Depends(Provide[Container.order_service]),
) -> OrderItem:
    """Edit a pending Order Item's quantity and/or note (AC1).

    Args:
        order_id: The id of the Order the item belongs to.
        item_id: The id of the Order Item to edit.
        payload: The submitted quantity and/or note.
        actor: The authenticated Waiter making the request.
        db: The active database session.
        order_service: Injected service handling the edit.

    Returns:
        The updated Order Item.

    Raises:
        OrderItemNotFoundError: Propagated from order_service, handled
            globally as a 404, if no Order Item matches item_id on order_id.
        OrderItemNotPendingError: Propagated from order_service, handled
            globally as a 409, if the item's status is not pending at the
            moment of the write (AC4).
    """
    return await order_service.edit_item(db, actor, order_id, item_id, payload)


@router.post(
    "/{order_id}/items/{item_id}/cancel",
    response_model=OrderItemResponse,
    responses=error_responses(_CANCEL_ITEM_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def cancel_order_item(
    order_id: OrderIdPath,
    item_id: ItemIdPath,
    actor: OrderItemCancelDep,
    db: SessionDep,
    order_service: OrderService = Depends(Provide[Container.order_service]),
) -> OrderItem:
    """Cancel a pending or in_preparation Order Item (AC2/AC3).

    Args:
        order_id: The id of the Order the item belongs to.
        item_id: The id of the Order Item to cancel.
        actor: The authenticated Waiter, Cook, or Admin making the request.
        db: The active database session.
        order_service: Injected service handling the cancel.

    Returns:
        The now-cancelled Order Item.

    Raises:
        OrderItemNotFoundError: Propagated from order_service, handled
            globally as a 404, if no Order Item matches item_id on order_id.
        OrderItemNotCancellableError: Propagated from order_service, handled
            globally as a 409, if the item's status is not pending or
            in_preparation at the moment of the write.
    """
    return await order_service.cancel_item(db, actor, order_id, item_id)


@router.post(
    "/{order_id}/items/{item_id}/pick-up",
    response_model=OrderItemResponse,
    responses=error_responses(_PICK_UP_ITEM_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def pick_up_order_item(
    order_id: OrderIdPath,
    item_id: ItemIdPath,
    actor: OrderItemProgressDep,
    db: SessionDep,
    order_service: OrderService = Depends(Provide[Container.order_service]),
) -> OrderItem:
    """Pick up a pending Order Item, deducting its Recipe's stock atomically (AC1, AC2, AC4, AC7, AC8).

    Args:
        order_id: The id of the Order the item belongs to.
        item_id: The id of the Order Item to pick up.
        actor: The authenticated Cook or Admin making the request.
        db: The active database session.
        order_service: Injected service handling the pick-up.

    Returns:
        The now in_preparation Order Item.

    Raises:
        OrderItemNotFoundError: Propagated from order_service, handled
            globally as a 404, if no Order Item matches item_id on order_id.
        IngredientNotFoundError: Propagated from order_service, handled
            globally as a 404, if the item's Dish recipe references an
            Ingredient that no longer exists.
        OrderItemNotPendingError: Propagated from order_service, handled
            globally as a 409, if the item's status is not pending at the
            moment of the write.
    """
    return await order_service.pick_up_item(db, actor, order_id, item_id)


@router.post(
    "/{order_id}/items/{item_id}/mark-ready",
    response_model=OrderItemResponse,
    responses=error_responses(_MARK_READY_ITEM_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def mark_order_item_ready(
    order_id: OrderIdPath,
    item_id: ItemIdPath,
    actor: OrderItemProgressDep,
    db: SessionDep,
    order_service: OrderService = Depends(Provide[Container.order_service]),
) -> OrderItem:
    """Mark an in_preparation Order Item ready, a pure status change (AC3, AC5, AC6, AC8).

    Args:
        order_id: The id of the Order the item belongs to.
        item_id: The id of the Order Item to mark ready.
        actor: The authenticated Cook or Admin making the request.
        db: The active database session.
        order_service: Injected service handling the mark-ready.

    Returns:
        The now ready Order Item.

    Raises:
        OrderItemNotFoundError: Propagated from order_service, handled
            globally as a 404, if no Order Item matches item_id on order_id.
        OrderItemNotInPreparationError: Propagated from order_service,
            handled globally as a 409, if the item's status is not
            in_preparation at the moment of the write.
    """
    return await order_service.mark_item_ready(db, actor, order_id, item_id)
