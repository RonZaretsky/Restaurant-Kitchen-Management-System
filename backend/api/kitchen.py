from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import KitchenItemResponse, User, UserRole
from services.kitchen_service import KitchenService

router = APIRouter(prefix="/api/kitchen", tags=["kitchen"])

KitchenReadDep = Annotated[User, Depends(require_role(UserRole.cook, UserRole.admin))]

_ERROR_DESCRIPTIONS = {
    401: "No valid session cookie was supplied",
    403: "Authenticated, but the caller's Role is not permitted for this action",
}


@router.get(
    "/items",
    response_model=list[KitchenItemResponse],
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403),
)
@inject
async def list_kitchen_items(
    actor: KitchenReadDep,
    db: SessionDep,
    kitchen_service: KitchenService = Depends(Provide[Container.kitchen_service]),
) -> list[KitchenItemResponse]:
    """List every non-cancelled Order Item currently active, grouped implicitly by Table.

    Args:
        actor: The authenticated Cook or Admin making the request.
        db: The active database session.
        kitchen_service: Injected service handling the read.

    Returns:
        Every non-cancelled Order Item, each carrying its own resolved table_id. An empty
        list is a valid, successful response ("no orders in the queue"), not a 404.
    """
    return await kitchen_service.list_active_items(db)
