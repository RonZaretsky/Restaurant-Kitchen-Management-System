import enum
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Not leading-underscore-private in the strict Python sense, just module-scoped by
# convention. Reusing it here (rather than duplicating the blank-after-strip check a
# second time) keeps that rule defined in exactly one place.
from .user import _strip_and_require_content


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
    created_at: datetime
    updated_at: datetime
