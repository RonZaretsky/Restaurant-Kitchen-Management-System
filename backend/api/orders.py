from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import Order, OrderResponse, User, UserRole
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

_ERROR_DESCRIPTIONS = {
    401: "No valid session cookie was supplied",
    403: "Authenticated, but the caller's Role is not waiter",
    404: "No matching Table was found",
    409: "The Table is not currently available",
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
