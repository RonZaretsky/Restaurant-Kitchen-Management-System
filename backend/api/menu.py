from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import (
    Category,
    CategoryResponse,
    CreateCategoryRequest,
    CreateDishRequest,
    CreateRecipeIngredientRequest,
    Dish,
    DishResponse,
    RecipeIngredient,
    RecipeIngredientResponse,
    UpdateDishRequest,
    UpdateRecipeIngredientRequest,
    User,
    UserRole,
)
from data_models.menu import _INT4_MAX
from services.menu_service import MenuService

router = APIRouter(prefix="/api/menu", tags=["menu"])

# Menu authoring is Admin-only (FR-22), unlike Story 2.1's InventoryWriteDep, which
# permitted two Roles. Do not widen this to warehouse_manager.
MenuDep = Annotated[User, Depends(require_role(UserRole.admin))]

# Reads permit Cook too (Story 2.5, FR-25): a Cook can browse the catalog and a
# Dish's recipe read-only, with zero write access to any of it. Kept separate
# from MenuDep so the three list/read routes below can widen independently of
# every write route, which all stay Admin-only.
MenuReadDep = Annotated[User, Depends(require_role(UserRole.admin, UserRole.cook))]

# The Dish list alone also permits a Waiter (Story 3.2, FR-5): a Waiter picks
# from the catalog to add items to an Order, so the Table/Order detail screen
# cannot render without this read. Deliberately narrower than widening
# MenuReadDep itself, which would also hand a Waiter every Dish's recipe
# (list_recipe_ingredients); nothing in FR-5 needs that, and recipes are
# kitchen-side detail. Same read-dep-split shape TablesReadDep used in Story 3.1.
DishCatalogReadDep = Annotated[
    User, Depends(require_role(UserRole.admin, UserRole.cook, UserRole.waiter))
]

# Path ids need the same int4 upper bound their request-body counterparts carry
# (trap 16). Without it a larger value reaches db.get and raises an unhandled
# asyncpg.DataError ("value out of int32 range"), a 500 rather than a clean 422.
DishIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]
IngredientIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]

_ERROR_DESCRIPTIONS = {
    401: "No valid session cookie was supplied",
    403: "Authenticated, but the caller's Role is not permitted for this action",
    404: "No matching Category, Dish, Ingredient, or Recipe Ingredient line was found",
    409: "The request conflicts with existing state (a duplicate name, an empty-recipe "
    "availability gate, a duplicate recipe ingredient, a unit that does not match the "
    "ingredient's own, removing a dish's last recipe ingredient while it is available, or "
    "adding a line against a deactivated ingredient)",
}


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403),
)
@inject
async def list_categories(
    actor: MenuReadDep,
    db: SessionDep,
    menu_service: MenuService = Depends(Provide[Container.menu_service]),
) -> list[Category]:
    """List every Menu Category.

    Args:
        actor: The authenticated Admin or Cook making the request.
        db: The active database session.
        menu_service: Injected service handling the read.

    Returns:
        Every Category.
    """
    return await menu_service.list_categories(db)


@router.get(
    "/dishes",
    response_model=list[DishResponse],
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403),
)
@inject
async def list_dishes(
    actor: DishCatalogReadDep,
    db: SessionDep,
    menu_service: MenuService = Depends(Provide[Container.menu_service]),
) -> list[Dish]:
    """List every Dish.

    Args:
        actor: The authenticated Admin, Cook, or Waiter making the request.
        db: The active database session.
        menu_service: Injected service handling the read.

    Returns:
        Every Dish.
    """
    return await menu_service.list_dishes(db)


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
    dish_id: DishIdPath,
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


@router.get(
    "/dishes/{dish_id}/recipe-ingredients",
    response_model=list[RecipeIngredientResponse],
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404),
)
@inject
async def list_recipe_ingredients(
    dish_id: DishIdPath,
    actor: MenuReadDep,
    db: SessionDep,
    menu_service: MenuService = Depends(Provide[Container.menu_service]),
) -> list[RecipeIngredient]:
    """List every Recipe Ingredient line for a Dish.

    Args:
        dish_id: The id of the Dish whose recipe is being read.
        actor: The authenticated Admin or Cook making the request.
        db: The active database session.
        menu_service: Injected service handling the read.

    Returns:
        Every Recipe Ingredient line for this Dish, always current (AC3).

    Raises:
        DishNotFoundError: Propagated from menu_service, handled globally as
            a 404, if no Dish matches dish_id.
    """
    return await menu_service.list_recipe_ingredients(db, actor, dish_id)


@router.post(
    "/dishes/{dish_id}/recipe-ingredients",
    response_model=RecipeIngredientResponse,
    status_code=201,
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def add_recipe_ingredient(
    dish_id: DishIdPath,
    payload: CreateRecipeIngredientRequest,
    actor: MenuDep,
    db: SessionDep,
    menu_service: MenuService = Depends(Provide[Container.menu_service]),
) -> RecipeIngredient:
    """Add a Recipe Ingredient line to a Dish (AC1).

    Args:
        dish_id: The id of the Dish the line is being added to.
        payload: The submitted ingredient, quantity, and unit.
        actor: The authenticated Admin making the request.
        db: The active database session.
        menu_service: Injected service handling the addition.

    Returns:
        The newly created Recipe Ingredient line.

    Raises:
        DishNotFoundError: Propagated from menu_service, handled globally as
            a 404, if no Dish matches dish_id.
        IngredientNotFoundError: Propagated from menu_service, handled
            globally as a 404, if no Ingredient matches payload.ingredient_id.
        DuplicateRecipeIngredientError: Propagated from menu_service, handled
            globally as a 409, if this Dish already has a line for this
            Ingredient.
    """
    return await menu_service.add_recipe_ingredient(db, actor, dish_id, payload)


@router.patch(
    "/dishes/{dish_id}/recipe-ingredients/{ingredient_id}",
    response_model=RecipeIngredientResponse,
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404),
)
@inject
async def update_recipe_ingredient(
    dish_id: DishIdPath,
    ingredient_id: IngredientIdPath,
    payload: UpdateRecipeIngredientRequest,
    actor: MenuDep,
    db: SessionDep,
    menu_service: MenuService = Depends(Provide[Container.menu_service]),
) -> RecipeIngredient:
    """Edit a Recipe Ingredient line's quantity and/or unit.

    Args:
        dish_id: The id of the Dish the line belongs to.
        ingredient_id: The id of the Ingredient identifying the line.
        payload: The fields to change.
        actor: The authenticated Admin making the request.
        db: The active database session.
        menu_service: Injected service handling the edit.

    Returns:
        The updated Recipe Ingredient line.

    Raises:
        RecipeIngredientNotFoundError: Propagated from menu_service, handled
            globally as a 404, if no line matches (dish_id, ingredient_id).
    """
    return await menu_service.update_recipe_ingredient(db, actor, dish_id, ingredient_id, payload)


@router.delete(
    "/dishes/{dish_id}/recipe-ingredients/{ingredient_id}",
    status_code=204,
    responses=error_responses(_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def remove_recipe_ingredient(
    dish_id: DishIdPath,
    ingredient_id: IngredientIdPath,
    actor: MenuDep,
    db: SessionDep,
    menu_service: MenuService = Depends(Provide[Container.menu_service]),
) -> None:
    """Remove a Recipe Ingredient line from a Dish (AC2).

    Args:
        dish_id: The id of the Dish the line belongs to.
        ingredient_id: The id of the Ingredient identifying the line.
        actor: The authenticated Admin making the request.
        db: The active database session.
        menu_service: Injected service handling the removal.

    Returns:
        Nothing.

    Raises:
        RecipeIngredientNotFoundError: Propagated from menu_service, handled
            globally as a 404, if no line matches (dish_id, ingredient_id).
        CannotRemoveLastRecipeIngredientError: Propagated from menu_service,
            handled globally as a 409, if this is the Dish's last line and
            the Dish is currently available.
    """
    await menu_service.remove_recipe_ingredient(db, actor, dish_id, ingredient_id)
