from collections.abc import Sequence
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import CreateOrderItemRequest, Order, OrderItem, OrderItemResponse, OrderResponse, User, UserRole
from data_models.menu import _INT4_MAX
from services.order_service import OrderService

router = APIRouter(prefix="/api/orders", tags=["orders"])

# Opening a table into an Order is Waiter-only (FR-4). Unlike every prior
# domain router (Admin-only, or Admin plus one other Role), this is the first
# route scoped to exactly one non-Admin Role with no Admin fallback.
OrdersDep = Annotated[User, Depends(require_role(UserRole.waiter))]

# Path ids need the same int4 upper bound their request-body counterparts carry
# (trap 16), matching api/tables.py's own TableIdPath.
TableIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]
OrderIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]

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
    404: "No matching Order was found",
    409: "The Dish is currently unavailable",
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
