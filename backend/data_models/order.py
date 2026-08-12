import enum
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Postgres's integer (int4) column range. table_number and capacity are both plain
# Integer columns; without this bound a value outside int4 range passes Pydantic and
# then raises an unhandled asyncpg.DataError ("value out of int32 range") on the
# query, a 500, instead of a clean 422 (trap 16).
_INT4_MAX = 2_147_483_647


class TableStatus(enum.Enum):
    available = "available"
    occupied = "occupied"
    reserved = "reserved"


class OrderStatus(enum.Enum):
    pending = "pending"
    in_preparation = "in_preparation"
    ready = "ready"
    served = "served"
    closed = "closed"


class OrderItemStatus(enum.Enum):
    pending = "pending"
    in_preparation = "in_preparation"
    ready = "ready"


class RestaurantTable(Base):
    __tablename__ = "restaurant_tables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TableStatus] = mapped_column(Enum(TableStatus), nullable=False, default=TableStatus.available)


class CreateTableRequest(BaseModel):
    """Body of an Admin's request to create a Restaurant Table."""

    table_number: int = Field(gt=0, le=_INT4_MAX)
    capacity: int = Field(gt=0, le=_INT4_MAX)


class UpdateTableRequest(BaseModel):
    """Body of an Admin's request to edit a Table's number and/or capacity.

    At least one field must be provided, mirroring UpdateDishRequest's shape.
    """

    table_number: int | None = Field(default=None, gt=0, le=_INT4_MAX)
    capacity: int | None = Field(default=None, gt=0, le=_INT4_MAX)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateTableRequest":
        """Reject an update that changes nothing.

        Returns:
            This instance, unchanged, if at least one field is set.

        Raises:
            ValueError: If every field is None.
        """
        if self.table_number is None and self.capacity is None:
            raise ValueError("at least one field must be provided")
        return self


class TableResponse(BaseModel):
    """Body of any tables endpoint response describing a Restaurant Table."""

    model_config = {"from_attributes": True}

    id: int
    table_number: int
    capacity: int
    status: TableStatus


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(Integer, ForeignKey("restaurant_tables.id"), nullable=False)
    waiter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), nullable=False, default=OrderStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    dish_id: Mapped[int] = mapped_column(Integer, ForeignKey("dishes.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[OrderItemStatus] = mapped_column(Enum(OrderItemStatus), nullable=False, default=OrderItemStatus.pending)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cook_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
