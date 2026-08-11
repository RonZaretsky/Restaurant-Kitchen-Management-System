from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import CreateIngredientRequest, Ingredient, IngredientResponse, User, UserRole
from services.inventory_service import InventoryService

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

# The first route to permit more than one Role: a Warehouse Manager or an Admin
# may create an Ingredient (FR-16). require_role's existing *roles signature
# already supports this without any change to api/dependencies.py.
InventoryWriteDep = Annotated[
    User, Depends(require_role(UserRole.admin, UserRole.warehouse_manager))
]

_ERROR_DESCRIPTIONS = {
    401: "No valid session cookie was supplied",
    403: "Authenticated, but the caller's Role is neither admin nor warehouse_manager",
    409: "An ingredient with this name already exists",
}


@router.post(
    "/ingredients",
    response_model=IngredientResponse,
    status_code=201,
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 409),
)
@inject
async def create_ingredient(
    payload: CreateIngredientRequest,
    actor: InventoryWriteDep,
    db: SessionDep,
    inventory_service: InventoryService = Depends(Provide[Container.inventory_service]),
) -> Ingredient:
    """Create a new Ingredient record.

    Args:
        payload: The submitted name, unit, threshold, and initial stock.
        actor: The authenticated Warehouse Manager or Admin making the request.
        db: The active database session.
        inventory_service: Injected service handling the creation.

    Returns:
        The newly created Ingredient.

    Raises:
        DuplicateIngredientNameError: Propagated from inventory_service,
            handled globally as a 409, if the name already exists.
    """
    return await inventory_service.create_ingredient(db, actor, payload)
