from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .user import _strip_and_require_content

# Postgres's integer (int4) column range. category_id and prep_time_minutes are both
# plain Integer columns; without this bound a value outside int4 range passes Pydantic
# and then raises an unhandled asyncpg.DataError ("value out of int32 range") on the
# query, a 500, instead of a clean 422.
_INT4_MAX = 2_147_483_647


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class Dish(Base):
    __tablename__ = "dishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    # False: a Dish starts unavailable until it has a recipe. The
    # service always passes is_available=False explicitly on create anyway, but the
    # column default should not itself claim otherwise for any insert path that
    # bypasses the service.
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prep_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # Nullable provenance link back to the AIRecipeSuggestion this Dish was confirmed from
    #. Null for a manually-defined Dish. Lives here, not on
    # RecipeIngredient, since there is no single row representing "the recipe" as a whole — a
    # Dish's recipe is its set of RecipeIngredient rows, and one Dish has at most one originating
    # suggestion.
    # unique=True: closes a TOCTOU race where two concurrent Dish
    # creations citing the same suggestion could both pass the service-level check before either
    # commits, giving one suggestion two confirming Dishes. Postgres permits multiple NULLs
    # under a plain UNIQUE constraint, so ordinary (non-AI-sourced) Dishes are unaffected.
    source_suggestion_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_recipe_suggestions.id"), nullable=True, unique=True
    )


class CreateCategoryRequest(BaseModel):
    """Body of an Admin's request to create a Menu Category."""

    name: str = Field(min_length=1, max_length=50)

    _strip_name = field_validator("name")(_strip_and_require_content)


class CategoryResponse(BaseModel):
    """Body of any menu endpoint response describing a Menu Category."""

    model_config = {"from_attributes": True}

    id: int
    name: str


class CreateDishRequest(BaseModel):
    """Body of an Admin's request to create a Dish.

    Never carries is_available: a newly created Dish is unconditionally
    unavailable until it has a recipe, regardless of anything a
    caller submits.
    """

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    # max_digits/decimal_places match the Numeric(8, 2) column exactly. Without
    # them, a value with more digits than the column allows passes validation
    # here and then raises an unhandled asyncpg.NumericValueOutOfRangeError on
    # commit (a 500), the same class of bug the Ingredient bounds guard against.
    price: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    category_id: int = Field(gt=0, le=_INT4_MAX)
    prep_time_minutes: int | None = Field(default=None, ge=0, le=_INT4_MAX)
    # Optional: set only when this Dish is being confirmed from a Recipe
    # Suggestion. Every existing call site omits this and is unaffected.
    source_suggestion_id: int | None = Field(default=None, gt=0, le=_INT4_MAX)

    _strip_name = field_validator("name")(_strip_and_require_content)


class UpdateDishRequest(BaseModel):
    """Body of an Admin's request to edit a Dish's fields and/or availability.

    At least one field must be provided, mirroring UpdateUserRequest's shape.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=2)
    category_id: int | None = Field(default=None, gt=0, le=_INT4_MAX)
    prep_time_minutes: int | None = Field(default=None, ge=0, le=_INT4_MAX)
    is_available: bool | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        """Trim and validate name only when it was actually provided.

        Unlike CreateDishRequest's required name, this field is optional, so
        an explicit null must pass through unchanged rather than reaching
        _strip_and_require_content, which assumes a str and would raise an
        unhandled AttributeError on None instead of a clean 422.

        Args:
            value: The submitted name, or None if not being changed.

        Returns:
            The trimmed name, or None unchanged.

        Raises:
            ValueError: If value is a blank-after-strip string.
        """
        if value is None:
            return value
        return _strip_and_require_content(value)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateDishRequest":
        """Reject an update that changes nothing.

        Returns:
            This instance, unchanged, if at least one field is set.

        Raises:
            ValueError: If every field is None.
        """
        if all(
            value is None
            for value in (
                self.name,
                self.description,
                self.price,
                self.category_id,
                self.prep_time_minutes,
                self.is_available,
            )
        ):
            raise ValueError("at least one field must be provided")
        return self


class DishResponse(BaseModel):
    """Body of any menu endpoint response describing a Dish."""

    model_config = {"from_attributes": True}

    id: int
    name: str
    description: str | None
    price: Decimal
    category_id: int
    is_available: bool
    prep_time_minutes: int | None
    created_at: datetime
    source_suggestion_id: int | None
