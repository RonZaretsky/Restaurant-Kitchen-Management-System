import enum
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Not leading-underscore-private in the strict Python sense, just module-scoped by
# convention. Reusing it here (rather than duplicating the blank-after-strip check a
# second time) keeps that rule defined in exactly one place.
from .user import _strip_and_require_content

# Reused from menu.py rather than redefined here: ingredient_id is a plain-Integer FK,
# same int4 upper bound reasoning as menu.py's category_id (trap 16).
from .menu import _INT4_MAX


class Unit(enum.Enum):
    kg = "kg"
    liter = "liter"
    piece = "piece"


class Ingredient(Base):
    __tablename__ = "ingredients"
    __table_args__ = (
        # Layered on top of the column's own unique=True (case-sensitive), the same
        # shape Story 1.3 used for User.username, so "Tomato" and "tomato" cannot
        # coexist as two rows.
        Index("uq_ingredients_name_lower", text("lower(name)"), unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    unit: Mapped[Unit] = mapped_column(Enum(Unit), nullable=False)
    current_stock: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    min_stock_threshold: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    # Soft-deactivate (mirrors User.is_active exactly): flipping this never deletes or reassigns
    # the row, so every historical Recipe Ingredient line and Stock Movement referencing this
    # Ingredient stays intact. Not a CreateIngredientRequest field — always True at creation,
    # never caller-supplied, same as User.is_active.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    dish_id: Mapped[int] = mapped_column(Integer, ForeignKey("dishes.id"), primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(Integer, ForeignKey("ingredients.id"), primary_key=True)
    unit: Mapped[Unit] = mapped_column(Enum(Unit), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)


class CreateIngredientRequest(BaseModel):
    """Body of a Warehouse Manager's or Admin's request to create an Ingredient."""

    name: str = Field(min_length=1, max_length=100)
    unit: Unit
    # max_digits/decimal_places match the Numeric(10, 3) column exactly. Without
    # them, a value with more digits than the column allows passes validation
    # here and then raises an unhandled asyncpg.NumericValueOutOfRangeError on
    # commit (a 500), instead of the 422 this bound turns it into.
    min_stock_threshold: Decimal = Field(ge=0, max_digits=10, decimal_places=3)
    current_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=3)

    _strip_name = field_validator("name")(_strip_and_require_content)


class IngredientResponse(BaseModel):
    """Body of any inventory endpoint response describing an Ingredient."""

    model_config = {"from_attributes": True}

    id: int
    name: str
    unit: Unit
    current_stock: Decimal
    min_stock_threshold: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateRecipeIngredientRequest(BaseModel):
    """Body of an Admin's request to add a Recipe Ingredient line to a Dish."""

    ingredient_id: int = Field(gt=0, le=_INT4_MAX)
    # max_digits/decimal_places match RecipeIngredient.quantity's Numeric(10, 3)
    # column exactly, same reasoning as CreateIngredientRequest's bounds (trap 16).
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    unit: Unit


class UpdateRecipeIngredientRequest(BaseModel):
    """Body of an Admin's request to edit a Recipe Ingredient line's quantity and/or unit.

    At least one field must be provided, mirroring UpdateDishRequest's shape.
    """

    quantity: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    unit: Unit | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateRecipeIngredientRequest":
        """Reject an update that changes nothing.

        Returns:
            This instance, unchanged, if at least one field is set.

        Raises:
            ValueError: If every field is None.
        """
        if self.quantity is None and self.unit is None:
            raise ValueError("at least one field must be provided")
        return self


class RecipeIngredientResponse(BaseModel):
    """Body of any menu endpoint response describing a Recipe Ingredient line.

    Maps 1:1 to RecipeIngredient's own columns, matching CategoryResponse and
    DishResponse's precedent of not enriching a response with joined data.
    """

    model_config = {"from_attributes": True}

    dish_id: int
    ingredient_id: int
    quantity: Decimal
    unit: Unit
