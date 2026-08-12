from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import (
    Category,
    CategoryResponse,
    CreateCategoryRequest,
    CreateDishRequest,
    Dish,
    DishResponse,
    UpdateDishRequest,
    User,
    UserRole,
)
from services.menu_service import MenuService

router = APIRouter(prefix="/api/menu", tags=["menu"])

# Menu authoring is Admin-only (FR-22), unlike Story 2.1's InventoryWriteDep, which
# permitted two Roles. Do not widen this to warehouse_manager.
MenuDep = Annotated[User, Depends(require_role(UserRole.admin))]

_ERROR_DESCRIPTIONS = {
    401: "No valid session cookie was supplied",
    403: "Authenticated, but the caller's Role is not admin",
    404: "No matching Category or Dish was found",
    409: "The request conflicts with existing state",
}


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=201,
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 409),
)
@inject
async def create_category(
    payload: CreateCategoryRequest,
    actor: MenuDep,
    db: SessionDep,
    menu_service: MenuService = Depends(Provide[Container.menu_service]),
) -> Category:
    """Create a new Menu Category.

    Args:
        payload: The submitted category name.
        actor: The authenticated Admin making the request.
        db: The active database session.
        menu_service: Injected service handling the creation.

    Returns:
        The newly created Category.

    Raises:
        DuplicateCategoryNameError: Propagated from menu_service, handled
            globally as a 409, if the name already exists.
    """
    return await menu_service.create_category(db, actor, payload)


@router.post(
    "/dishes",
    response_model=DishResponse,
    status_code=201,
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404),
)
@inject
async def create_dish(
    payload: CreateDishRequest,
    actor: MenuDep,
    db: SessionDep,
    menu_service: MenuService = Depends(Provide[Container.menu_service]),
) -> Dish:
    """Create a new Dish, unconditionally unavailable until it has a recipe.

    Args:
        payload: The submitted name, description, price, category, and prep
            time.
        actor: The authenticated Admin making the request.
        db: The active database session.
        menu_service: Injected service handling the creation.

    Returns:
        The newly created, unavailable Dish.

    Raises:
        CategoryNotFoundError: Propagated from menu_service, handled
            globally as a 404, if category_id does not match any Category.
    """
    return await menu_service.create_dish(db, actor, payload)


@router.patch(
    "/dishes/{dish_id}",
    response_model=DishResponse,
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def update_dish(
    dish_id: int,
    payload: UpdateDishRequest,
    actor: MenuDep,
    db: SessionDep,
    menu_service: MenuService = Depends(Provide[Container.menu_service]),
) -> Dish:
    """Edit a Dish's fields and/or availability.

    Args:
        dish_id: The id of the Dish to edit.
        payload: The fields to change.
        actor: The authenticated Admin making the request.
        db: The active database session.
        menu_service: Injected service handling the edit.

    Returns:
        The updated Dish.

    Raises:
        DishNotFoundError: Propagated from menu_service, handled globally as
            a 404, if no Dish matches dish_id.
        CategoryNotFoundError: Propagated from menu_service, handled
            globally as a 404, if category_id is changing and the new value
            does not match any Category.
        EmptyRecipeError: Propagated from menu_service, handled globally as
            a 409, if is_available is being set True while the Dish has
            zero Recipe Ingredient lines.
    """
    return await menu_service.update_dish(db, actor, dish_id, payload)
