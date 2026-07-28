import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Unit(enum.Enum):
    kg = "kg"
    liter = "liter"
    piece = "piece"


class Ingredient(Base):
    __tablename__ = "ingredients"

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
