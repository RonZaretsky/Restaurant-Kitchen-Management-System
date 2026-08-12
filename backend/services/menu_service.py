from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import (
    Category,
    CreateCategoryRequest,
    CreateDishRequest,
    Dish,
    RecipeIngredient,
    UpdateDishRequest,
    User,
)
from exceptions import (
    CategoryNotFoundError,
    DishNotFoundError,
    DuplicateCategoryNameError,
    EmptyRecipeError,
)


class MenuService:
    """Creates and manages Menu Categories and Dishes.

    Config-free, so it is registered as a container-level Factory with only
    the logger injected, matching InventoryService's shape.
    """

    def __init__(self, logger: Any) -> None:
        """Initialize the service.

        Args:
            logger: The loguru logger injected from the container.
        """
        self._logger = logger

    async def create_category(
        self, db: AsyncSession, actor: User, payload: CreateCategoryRequest
    ) -> Category:
        """Create a new Menu Category.

        Category names are unique case-sensitively only, unlike Ingredient
        names or usernames: no epics AC or UX doc pairs categories into that
        case-insensitive-duplicate convention.

        Args:
            db: The active database session.
            actor: The Admin performing the creation, used only for logging.
            payload: The submitted category name.

        Returns:
            The newly created Category.

        Raises:
            DuplicateCategoryNameError: If the name already exists.
        """
        existing = await db.execute(select(Category).where(Category.name == payload.name))
        if existing.scalar_one_or_none() is not None:
            self._logger.warning(
                "Category creation rejected by user_id={}: name={} already exists",
                actor.id,
                payload.name,
            )
            raise DuplicateCategoryNameError()

        category = Category(name=payload.name)
        db.add(category)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            self._logger.warning(
                "Category creation rejected by user_id={}: name={} already exists (lost the race)",
                actor.id,
                payload.name,
            )
            raise DuplicateCategoryNameError() from exc
        await db.refresh(category)
        self._logger.info(
            "Category created by user_id={}: category_id={} name={}",
            actor.id,
            category.id,
            category.name,
        )
        return category

    async def create_dish(self, db: AsyncSession, actor: User, payload: CreateDishRequest) -> Dish:
        """Create a new Dish, unconditionally unavailable (AC2, AD-8).

        Args:
            db: The active database session.
            actor: The Admin performing the creation, used only for logging.
            payload: The submitted name, description, price, category, and
                prep time.

        Returns:
            The newly created, unavailable Dish.

        Raises:
            CategoryNotFoundError: If category_id does not match any Category.
        """
        await self._get_category(db, actor, payload.category_id)

        dish = Dish(
            name=payload.name,
            description=payload.description,
            price=payload.price,
            category_id=payload.category_id,
            prep_time_minutes=payload.prep_time_minutes,
            is_available=False,
        )
        db.add(dish)
        await db.commit()
        await db.refresh(dish)
        self._logger.info(
            "Dish created by user_id={}: dish_id={} name={} category_id={}",
            actor.id,
            dish.id,
            dish.name,
            dish.category_id,
        )
        return dish

    async def get_dish(self, db: AsyncSession, actor: User, dish_id: int) -> Dish:
        """Fetch a single Dish by id.

        Every by-id lookup below funnels through here, mirroring
        UserService.get_user.

        Args:
            db: The active database session.
            actor: The Admin performing the lookup, used only for logging.
            dish_id: The id of the Dish to fetch.

        Returns:
            The matching Dish.

        Raises:
            DishNotFoundError: If no Dish matches dish_id.
        """
        dish = await db.get(Dish, dish_id)
        if dish is None:
            self._logger.warning(
                "Admin action rejected for user_id={}: no dish with dish_id={}",
                actor.id,
                dish_id,
            )
            raise DishNotFoundError()
        return dish

    async def update_dish(
        self, db: AsyncSession, actor: User, dish_id: int, payload: UpdateDishRequest
    ) -> Dish:
        """Edit a Dish's fields and/or availability.

        Setting is_available to True is rejected while the Dish has zero
        Recipe Ingredient lines (AD-8). No Recipe-management story has
        shipped yet, so this count is always 0 today, every Dish stays
        unavailable until Story 2.3 lands, that is expected sequencing.

        Args:
            db: The active database session.
            actor: The Admin performing the edit, used only for logging.
            dish_id: The id of the Dish to edit.
            payload: The fields to change. At least one is always set,
                enforced by UpdateDishRequest's own validation.

        Returns:
            The updated Dish.

        Raises:
            DishNotFoundError: If no Dish matches dish_id.
            CategoryNotFoundError: If category_id is changing and the new
                value does not match any Category.
            EmptyRecipeError: If is_available is being set True while the
                Dish has zero Recipe Ingredient lines.
        """
        dish = await self.get_dish(db, actor, dish_id)

        changed_fields: list[str] = []

        if payload.category_id is not None and payload.category_id != dish.category_id:
            await self._get_category(db, actor, payload.category_id)
            dish.category_id = payload.category_id
            changed_fields.append("category_id")

        if payload.is_available is not None and payload.is_available != dish.is_available:
            if payload.is_available:
                await self._reject_if_recipe_empty(db, dish, actor)
            dish.is_available = payload.is_available
            changed_fields.append("is_available")

        if payload.name is not None and payload.name != dish.name:
            dish.name = payload.name
            changed_fields.append("name")

        if payload.description is not None and payload.description != dish.description:
            dish.description = payload.description
            changed_fields.append("description")

        if payload.price is not None and payload.price != dish.price:
            dish.price = payload.price
            changed_fields.append("price")

        if payload.prep_time_minutes is not None and payload.prep_time_minutes != dish.prep_time_minutes:
            dish.prep_time_minutes = payload.prep_time_minutes
            changed_fields.append("prep_time_minutes")

        # An edit submitting the values already stored is not a state change, and
        # the audit log must not claim one, mirroring UserService.update_user.
        if not changed_fields:
            return dish

        await db.commit()
        await db.refresh(dish)
        self._logger.info(
            "Dish updated by user_id={}: dish_id={} changed_fields={}",
            actor.id,
            dish.id,
            changed_fields,
        )
        return dish

    async def _get_category(self, db: AsyncSession, actor: User, category_id: int) -> Category:
        """Fetch a single Category by id, or raise if it does not exist.

        Args:
            db: The active database session.
            actor: The Admin performing the action, used only for logging.
            category_id: The id to look up.

        Returns:
            The matching Category.

        Raises:
            CategoryNotFoundError: If no Category matches category_id.
        """
        category = await db.get(Category, category_id)
        if category is None:
            self._logger.warning(
                "Admin action rejected for user_id={}: no category with category_id={}",
                actor.id,
                category_id,
            )
            raise CategoryNotFoundError()
        return category

    async def _reject_if_recipe_empty(self, db: AsyncSession, dish: Dish, actor: User) -> None:
        """Raise EmptyRecipeError if dish has zero Recipe Ingredient lines.

        Args:
            db: The active database session.
            dish: The Dish being considered for availability.
            actor: The Admin attempting the action, used only for logging.

        Returns:
            Nothing, if at least one Recipe Ingredient line exists.

        Raises:
            EmptyRecipeError: If dish has zero Recipe Ingredient lines.
        """
        result = await db.execute(
            select(func.count()).where(RecipeIngredient.dish_id == dish.id)
        )
        if result.scalar_one() == 0:
            self._logger.warning(
                "Availability rejected for user_id={}: dish_id={} has no recipe ingredients",
                actor.id,
                dish.id,
            )
            raise EmptyRecipeError()
