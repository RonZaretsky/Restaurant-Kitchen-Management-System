from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import (
    CreateTableRequest,
    RestaurantTable,
    TableResponse,
    UpdateTableRequest,
    User,
    UserRole,
)
from data_models.menu import _INT4_MAX
from services.table_service import TableService

router = APIRouter(prefix="/api/tables", tags=["tables"])

# Table management (create/edit) is Admin-only, same shape as MenuDep,
# not InventoryWriteDep's two-Role form.
TablesDep = Annotated[User, Depends(require_role(UserRole.admin))]

# Reads permit a Waiter too: a Waiter needs to see every
# Table's status to open one into a new Order. Mirrors MenuReadDep/
# InventoryReadDep's established split between a read-only dependency and a
# write-only one. Widened again to include a Cook: the Kitchen Display
# resolves each card's table_number client-side via this same endpoint. The
# same incremental-widening pattern InventoryReadDep/DishCatalogReadDep/
# MenuReadDep have each already gone through.
TablesReadDep = Annotated[User, Depends(require_role(UserRole.admin, UserRole.waiter, UserRole.cook))]

# Path ids need the same int4 upper bound their request-body counterparts carry
# so an out-of-range value 422s instead of 500ing.
TableIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]

_ERROR_DESCRIPTIONS = {
    401: "No valid session cookie was supplied",
    403: "Authenticated, but the caller's Role is not permitted for this action",
    404: "No matching Table was found",
    409: "The request conflicts with existing state (a duplicate table number, or "
    "the table is not available)",
}


@router.get(
    "",
    response_model=list[TableResponse],
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403),
)
@inject
async def list_tables(
    actor: TablesReadDep,
    db: SessionDep,
    table_service: TableService = Depends(Provide[Container.table_service]),
) -> list[RestaurantTable]:
    """List every Restaurant Table.

    Args:
        actor: The authenticated Admin or Waiter making the request.
        db: The active database session.
        table_service: Injected service handling the read.

    Returns:
        Every Restaurant Table.
    """
    return await table_service.list_tables(db)


@router.post(
    "",
    response_model=TableResponse,
    status_code=201,
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 409),
)
@inject
async def create_table(
    payload: CreateTableRequest,
    actor: TablesDep,
    db: SessionDep,
    table_service: TableService = Depends(Provide[Container.table_service]),
) -> RestaurantTable:
    """Create a new Restaurant Table, starting available.

    Args:
        payload: The submitted table number and capacity.
        actor: The authenticated Admin making the request.
        db: The active database session.
        table_service: Injected service handling the creation.

    Returns:
        The newly created, available Restaurant Table.

    Raises:
        DuplicateTableNumberError: Propagated from table_service, handled
            globally as a 409, if the table number already exists.
    """
    return await table_service.create_table(db, actor, payload)


@router.patch(
    "/{table_id}",
    response_model=TableResponse,
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def update_table(
    table_id: TableIdPath,
    payload: UpdateTableRequest,
    actor: TablesDep,
    db: SessionDep,
    table_service: TableService = Depends(Provide[Container.table_service]),
) -> RestaurantTable:
    """Edit a Table's number and/or capacity, only while it is available.

    Args:
        table_id: The id of the Table to edit.
        payload: The fields to change.
        actor: The authenticated Admin making the request.
        db: The active database session.
        table_service: Injected service handling the edit.

    Returns:
        The updated Restaurant Table.

    Raises:
        TableNotFoundError: Propagated from table_service, handled globally
            as a 404, if no Table matches table_id.
        DuplicateTableNumberError: Propagated from table_service, handled
            globally as a 409, if table_number is changing and another Table
            already uses the new value.
        TableInUseError: Propagated from table_service, handled globally as
            a 409, if the Table's status is not available at the moment of
            the write.
    """
    return await table_service.update_table(db, actor, table_id, payload)
