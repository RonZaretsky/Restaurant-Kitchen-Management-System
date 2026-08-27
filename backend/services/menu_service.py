from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data_models import (
    AIRecipeSuggestion,
    Category,
    CreateCategoryRequest,
    CreateDishRequest,
    CreateRecipeIngredientRequest,
    Dish,
    Ingredient,
    RecipeIngredient,
    Unit,
    UpdateDishRequest,
    UpdateRecipeIngredientRequest,
    User,
)
from exceptions import (
    CannotRemoveLastRecipeIngredientError,
    CategoryNotFoundError,
    DishNotFoundError,
    DuplicateCategoryNameError,
    DuplicateRecipeIngredientError,
    EmptyRecipeError,
    IngredientNotActiveError,
    IngredientNotFoundError,
    RecipeIngredientNotFoundError,
    SuggestionAlreadyConfirmedError,
    SuggestionAlreadyDismissedError,
    SuggestionNotFoundError,
    UnitMismatchError,
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
            # Logging before rollback, not after: rollback() expires every object
            # bound to this session, actor included, so reading actor.id afterward
            # raises an unhandled MissingGreenlet.
            self._logger.warning(
                "Category creation rejected by user_id={}: name={} already exists (lost the race)",
                actor.id,
                payload.name,
            )
            await db.rollback()
            raise DuplicateCategoryNameError() from exc
        await db.refresh(category)
        self._logger.info(
            "Category created by user_id={}: category_id={} name={}",
            actor.id,
            category.id,
            category.name,
        )
        return category

    async def list_categories(self, db: AsyncSession) -> Sequence[Category]:
        """List every Menu Category.

        No actor argument: a plain unfiltered read has nothing to reject and
        nothing worth auditing, permissions are Role-level only.

        Args:
            db: The active database session.

        Returns:
            Every Category row, in id order.
        """
        result = await db.execute(select(Category).order_by(Category.id))
        return result.scalars().all()

    async def create_dish(self, db: AsyncSession, actor: User, payload: CreateDishRequest) -> Dish:
        """Create a new Dish, unconditionally unavailable (AC2, AD-8).

        Optionally confirms this Dish as originating from a Recipe Suggestion
        (Story 6.2, FR-19) when `payload.source_suggestion_id` is set — this is the
        *only* code path that can ever set that provenance link (AC2): there is no
        second, separate "confirm" mutation, just this one optional field on the
        same insert every Dish creation already goes through.

        Args:
            db: The active database session.
            actor: The Admin performing the creation, used only for logging.
            payload: The submitted name, description, price, category, prep
                time, and optional source Recipe Suggestion id.

        Returns:
            The newly created, unavailable Dish.

        Raises:
            CategoryNotFoundError: If category_id does not match any Category.
            SuggestionNotFoundError: If source_suggestion_id is set but matches no
                Recipe Suggestion.
            SuggestionAlreadyDismissedError: If the referenced suggestion has
                already been dismissed.
            SuggestionAlreadyConfirmedError: If another Dish already cites the
                referenced suggestion as its source.
        """
        await self._get_category(db, actor, payload.category_id)

        if payload.source_suggestion_id is not None:
            await self._validate_source_suggestion(db, actor, payload.source_suggestion_id)

        dish = Dish(
            name=payload.name,
            description=payload.description,
            price=payload.price,
            category_id=payload.category_id,
            prep_time_minutes=payload.prep_time_minutes,
            is_available=False,
            source_suggestion_id=payload.source_suggestion_id,
        )
        db.add(dish)
        try:
            await db.commit()
        except IntegrityError as exc:
            # The pre-check above loses to a concurrent create_dish citing the same
            # suggestion_id: uq_dishes_source_suggestion_id (code review finding) is the real
            # arbiter, so translate its violation into the same 409 rather than letting it
            # surface as a 500. Logging before rollback, not after: rollback() expires every
            # object bound to this session, actor included, so reading actor.id afterward raises
            # an unhandled MissingGreenlet.
            self._logger.warning(
                "Dish creation rejected by user_id={}: suggestion_id={} already confirmed (lost the race)",
                actor.id,
                payload.source_suggestion_id,
            )
            await db.rollback()
            raise SuggestionAlreadyConfirmedError() from exc
        await db.refresh(dish)
        self._logger.info(
            "Dish created by user_id={}: dish_id={} name={} category_id={} source_suggestion_id={}",
            actor.id,
            dish.id,
            dish.name,
            dish.category_id,
            dish.source_suggestion_id,
        )
        return dish

    async def _validate_source_suggestion(self, db: AsyncSession, actor: User, suggestion_id: int) -> None:
        """Validate a Recipe Suggestion id supplied on a Dish create (Story 6.2, FR-19).

        Args:
            db: The active database session.
            actor: The Admin performing the creation, used only for logging.
            suggestion_id: The Recipe Suggestion id to validate.

        Raises:
            SuggestionNotFoundError: If no Recipe Suggestion matches suggestion_id.
            SuggestionAlreadyDismissedError: If the suggestion is already dismissed.
            SuggestionAlreadyConfirmedError: If another Dish already cites this
                suggestion as its source.
        """
        suggestion = await db.get(AIRecipeSuggestion, suggestion_id)
        if suggestion is None:
            self._logger.warning(
                "Dish creation rejected for user_id={}: no suggestion with suggestion_id={}",
                actor.id,
                suggestion_id,
            )
            raise SuggestionNotFoundError()

        if suggestion.dismissed:
            self._logger.warning(
                "Dish creation rejected for user_id={}: suggestion_id={} is dismissed",
                actor.id,
                suggestion_id,
            )
            raise SuggestionAlreadyDismissedError()

        existing = await db.execute(select(Dish).where(Dish.source_suggestion_id == suggestion_id))
        if existing.scalar_one_or_none() is not None:
            self._logger.warning(
                "Dish creation rejected for user_id={}: suggestion_id={} already confirmed",
                actor.id,
                suggestion_id,
            )
            raise SuggestionAlreadyConfirmedError()

    async def list_dishes(self, db: AsyncSession) -> Sequence[Dish]:
        """List every Dish.

        No actor argument, same reasoning as list_categories.

        Args:
            db: The active database session.

        Returns:
            Every Dish row, in id order.
        """
        result = await db.execute(select(Dish).order_by(Dish.id))
        return result.scalars().all()

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

    async def list_recipe_ingredients(
        self, db: AsyncSession, actor: User, dish_id: int
    ) -> Sequence[RecipeIngredient]:
        """List every Recipe Ingredient line for a Dish.

        A plain SELECT against current state every call, never cached, so it
        can never return a stale snapshot (AC3).

        Args:
            db: The active database session.
            actor: The Admin performing the lookup, used only for logging.
            dish_id: The id of the Dish whose recipe is being read.

        Returns:
            Every RecipeIngredient row for this Dish.

        Raises:
            DishNotFoundError: If no Dish matches dish_id.
        """
        await self.get_dish(db, actor, dish_id)
        result = await db.execute(
            select(RecipeIngredient)
            .where(RecipeIngredient.dish_id == dish_id)
            .order_by(RecipeIngredient.ingredient_id)
        )
        return result.scalars().all()

    async def add_recipe_ingredient(
        self, db: AsyncSession, actor: User, dish_id: int, payload: CreateRecipeIngredientRequest
    ) -> RecipeIngredient:
        """Add a Recipe Ingredient line to a Dish.

        Args:
            db: The active database session.
            actor: The Admin performing the addition, used only for logging.
            dish_id: The id of the Dish the line is being added to.
            payload: The submitted ingredient, quantity, and unit.

        Returns:
            The newly created Recipe Ingredient line.

        Raises:
            DishNotFoundError: If no Dish matches dish_id.
            IngredientNotFoundError: If no Ingredient matches payload.ingredient_id.
            IngredientNotActiveError: If the Ingredient is currently deactivated (Story #3/#4) —
                only a *new* line is blocked; an existing line against an Ingredient deactivated
                later is untouched.
            UnitMismatchError: If payload.unit differs from the Ingredient's
                own unit.
            DuplicateRecipeIngredientError: If this Dish already has a line
                for this Ingredient.
        """
        await self.get_dish(db, actor, dish_id)
        ingredient = await self._get_ingredient(db, actor, payload.ingredient_id)
        if not ingredient.is_active:
            self._logger.warning(
                "Recipe ingredient addition rejected by user_id={}: dish_id={} ingredient_id={} "
                "is deactivated",
                actor.id,
                dish_id,
                payload.ingredient_id,
            )
            raise IngredientNotActiveError()
        self._reject_if_unit_mismatched(ingredient, payload.unit, actor, dish_id)

        existing = await db.get(RecipeIngredient, (dish_id, payload.ingredient_id))
        if existing is not None:
            self._logger.warning(
                "Recipe ingredient addition rejected by user_id={}: dish_id={} already has ingredient_id={}",
                actor.id,
                dish_id,
                payload.ingredient_id,
            )
            raise DuplicateRecipeIngredientError()

        line = RecipeIngredient(
            dish_id=dish_id,
            ingredient_id=payload.ingredient_id,
            quantity=payload.quantity,
            unit=payload.unit,
        )
        db.add(line)
        try:
            await db.commit()
        except IntegrityError as exc:
            # The check above loses to a concurrent add of the same line.
            # The composite primary key is the real arbiter, so translate its
            # violation into the same 409 rather than letting it surface as a 500.
            # Logging before rollback, not after: rollback() expires every object
            # bound to this session, actor included, so reading actor.id afterward
            # raises an unhandled MissingGreenlet.
            self._logger.warning(
                "Recipe ingredient addition rejected by user_id={}: dish_id={} already has "
                "ingredient_id={} (lost the race)",
                actor.id,
                dish_id,
                payload.ingredient_id,
            )
            await db.rollback()
            raise DuplicateRecipeIngredientError() from exc
        await db.refresh(line)
        self._logger.info(
            "Recipe ingredient added by user_id={}: dish_id={} ingredient_id={} quantity={} unit={}",
            actor.id,
            dish_id,
            line.ingredient_id,
            line.quantity,
            line.unit.value,
        )
        return line

    async def update_recipe_ingredient(
        self,
        db: AsyncSession,
        actor: User,
        dish_id: int,
        ingredient_id: int,
        payload: UpdateRecipeIngredientRequest,
    ) -> RecipeIngredient:
        """Edit a Recipe Ingredient line's quantity and/or unit.

        Args:
            db: The active database session.
            actor: The Admin performing the edit, used only for logging.
            dish_id: The id of the Dish the line belongs to.
            ingredient_id: The id of the Ingredient identifying the line.
            payload: The fields to change. At least one is always set,
                enforced by UpdateRecipeIngredientRequest's own validation.

        Returns:
            The updated Recipe Ingredient line.

        Raises:
            DishNotFoundError: If no Dish matches dish_id.
            RecipeIngredientNotFoundError: If no line matches
                (dish_id, ingredient_id).
            UnitMismatchError: If payload.unit differs from the Ingredient's
                own unit.
        """
        # Checked before the line itself so a bad dish_id reports "Dish not found"
        # here too, matching what the other three verbs on this URL space return.
        await self.get_dish(db, actor, dish_id)
        line = await self._get_recipe_ingredient(db, actor, dish_id, ingredient_id)

        changed_fields: list[str] = []

        if payload.quantity is not None and payload.quantity != line.quantity:
            line.quantity = payload.quantity
            changed_fields.append("quantity")

        if payload.unit is not None and payload.unit != line.unit:
            ingredient = await self._get_ingredient(db, actor, ingredient_id)
            self._reject_if_unit_mismatched(ingredient, payload.unit, actor, dish_id)
            line.unit = payload.unit
            changed_fields.append("unit")

        # An edit submitting the values already stored is not a state change, and
        # the audit log must not claim one, mirroring update_dish's exact reasoning.
        if not changed_fields:
            return line

        await db.commit()
        await db.refresh(line)
        self._logger.info(
            "Recipe ingredient updated by user_id={}: dish_id={} ingredient_id={} changed_fields={}",
            actor.id,
            dish_id,
            ingredient_id,
            changed_fields,
        )
        return line

    async def remove_recipe_ingredient(
        self, db: AsyncSession, actor: User, dish_id: int, ingredient_id: int
    ) -> None:
        """Remove a Recipe Ingredient line from a Dish.

        Rejected while it is this Dish's last line and the Dish is currently
        available (AC2, AD-8 second half): the Admin must mark it unavailable
        first.

        Args:
            db: The active database session.
            actor: The Admin performing the removal, used only for logging.
            dish_id: The id of the Dish the line belongs to.
            ingredient_id: The id of the Ingredient identifying the line.

        Returns:
            Nothing.

        Raises:
            RecipeIngredientNotFoundError: If no line matches
                (dish_id, ingredient_id).
            CannotRemoveLastRecipeIngredientError: If this is the Dish's last
                line and the Dish is currently available.
        """
        await self.get_dish(db, actor, dish_id)
        line = await self._get_recipe_ingredient(db, actor, dish_id, ingredient_id)
        dish = await self._lock_dish(db, dish_id)

        if dish.is_available:
            result = await db.execute(
                select(func.count()).where(RecipeIngredient.dish_id == dish_id)
            )
            if result.scalar_one() == 1:
                self._logger.warning(
                    "Recipe ingredient removal rejected by user_id={}: dish_id={} ingredient_id={} "
                    "is the last line while available",
                    actor.id,
                    dish_id,
                    ingredient_id,
                )
                raise CannotRemoveLastRecipeIngredientError()

        await db.delete(line)
        await db.commit()
        self._logger.info(
            "Recipe ingredient removed by user_id={}: dish_id={} ingredient_id={}",
            actor.id,
            dish_id,
            ingredient_id,
        )

    async def _lock_dish(self, db: AsyncSession, dish_id: int) -> Dish:
        """Lock a Dish row for the rest of the transaction and return it.

        Both halves of AD-8 read the Dish's availability and then count its
        Recipe Ingredient lines before deciding. Without a lock those are two
        unsynchronized reads: two admins deleting the last two lines of an
        available Dish both count 2, both pass the guard, and both commit,
        leaving an available Dish with an empty recipe. The same happens when
        a delete races an availability toggle, since each reads the other's
        pre-change state. Taking the same single row lock on both paths makes
        the second caller wait and re-evaluate against committed state.
        Locking one row by primary key gives every caller the same lock
        target, so they serialize instead of deadlocking (trap 9, the shape
        UserService's last-admin guard already uses).

        Args:
            db: The active database session.
            dish_id: The id of the Dish to lock.

        Returns:
            The locked Dish.

        Raises:
            DishNotFoundError: If no Dish matches dish_id.
        """
        result = await db.execute(select(Dish).where(Dish.id == dish_id).with_for_update())
        dish = result.scalar_one_or_none()
        if dish is None:
            raise DishNotFoundError()
        return dish

    def _reject_if_unit_mismatched(
        self, ingredient: Ingredient, unit: Unit, actor: User, dish_id: int
    ) -> None:
        """Raise UnitMismatchError if a line's unit is not the Ingredient's own unit.

        Nothing in this system converts between units, so a line recorded in
        a different unit than the ingredient is stocked in would make Epic 5's
        automatic deduction subtract the wrong amount with no error anywhere.

        Args:
            ingredient: The Ingredient the line refers to.
            unit: The unit submitted for the line.
            actor: The Admin attempting the action, used only for logging.
            dish_id: The Dish being edited, used only for logging.

        Returns:
            Nothing, if the units match.

        Raises:
            UnitMismatchError: If unit differs from the Ingredient's unit.
        """
        if unit != ingredient.unit:
            self._logger.warning(
                "Recipe ingredient rejected for user_id={}: dish_id={} ingredient_id={} "
                "submitted unit={} but ingredient is stocked in {}",
                actor.id,
                dish_id,
                ingredient.id,
                unit.value,
                ingredient.unit.value,
            )
            raise UnitMismatchError()

    async def _get_ingredient(self, db: AsyncSession, actor: User, ingredient_id: int) -> Ingredient:
        """Fetch a single Ingredient by id, or raise if it does not exist.

        Args:
            db: The active database session.
            actor: The Admin performing the action, used only for logging.
            ingredient_id: The id to look up.

        Returns:
            The matching Ingredient.

        Raises:
            IngredientNotFoundError: If no Ingredient matches ingredient_id.
        """
        ingredient = await db.get(Ingredient, ingredient_id)
        if ingredient is None:
            self._logger.warning(
                "Admin action rejected for user_id={}: no ingredient with ingredient_id={}",
                actor.id,
                ingredient_id,
            )
            raise IngredientNotFoundError()
        return ingredient

    async def _get_recipe_ingredient(
        self, db: AsyncSession, actor: User, dish_id: int, ingredient_id: int
    ) -> RecipeIngredient:
        """Fetch a single Recipe Ingredient line, or raise if it does not exist.

        Args:
            db: The active database session.
            actor: The Admin performing the action, used only for logging.
            dish_id: The id of the Dish the line should belong to.
            ingredient_id: The id of the Ingredient identifying the line.

        Returns:
            The matching Recipe Ingredient line.

        Raises:
            RecipeIngredientNotFoundError: If no line matches
                (dish_id, ingredient_id).
        """
        line = await db.get(RecipeIngredient, (dish_id, ingredient_id))
        if line is None:
            self._logger.warning(
                "Admin action rejected for user_id={}: no recipe ingredient for dish_id={} ingredient_id={}",
                actor.id,
                dish_id,
                ingredient_id,
            )
            raise RecipeIngredientNotFoundError()
        return line

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

        Locks the Dish row before counting, so this half of AD-8 serializes
        against the removal half (see _lock_dish). Without it, marking a Dish
        available and deleting its last line can interleave and both succeed.

        Args:
            db: The active database session.
            dish: The Dish being considered for availability.
            actor: The Admin attempting the action, used only for logging.

        Returns:
            Nothing, if at least one Recipe Ingredient line exists.

        Raises:
            EmptyRecipeError: If dish has zero Recipe Ingredient lines.
        """
        await self._lock_dish(db, dish.id)
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
