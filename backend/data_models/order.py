import enum
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Reused from menu.py rather than redefined: table_number and capacity are plain
# Integer columns needing the same int4 upper bound as menu.py's category_id
# (trap 16). recipe.py imports it the same way.
from .menu import _INT4_MAX


# The most portions of one Dish a single Order Item may carry. Keeps
# price_at_add * quantity inside Order.total_amount's Numeric(10, 2) range
# (FR-8/AD-7); see CreateOrderItemRequest. Mirrored by the frontend's own
# quantity parser so the two agree on what is submittable.
MAX_ORDER_ITEM_QUANTITY = 99


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
    cancelled = "cancelled"


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

    @field_validator("table_number", "capacity", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: object, info: ValidationInfo) -> object:
        """Reject a field explicitly submitted as null.

        An omitted field means "leave this alone", but an explicit null is a
        caller mistake, not a request to skip the field. Treating the two the
        same lets a browser silently send null for a field that failed to parse
        (JSON.stringify turns NaN into null) and get a 200 that applied only the
        other field, so the caller believes both were saved.

        Args:
            value: The submitted value, before coercion.
            info: Pydantic's field context, used for the field name.

        Returns:
            The value unchanged, if it is not an explicit null.

        Raises:
            ValueError: If the field was provided as null.
        """
        if value is None:
            raise ValueError(f"{info.field_name} must be a number, not null")
        return value

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
    price_at_add: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)


class OrderResponse(BaseModel):
    """Body of any orders endpoint response describing an Order."""

    model_config = {"from_attributes": True}

    id: int
    table_id: int
    waiter_id: int
    status: OrderStatus
    created_at: datetime
    closed_at: datetime | None
    total_amount: Decimal | None


class CreateOrderItemRequest(BaseModel):
    """Body of a Waiter's request to add an Order Item to an open Order.

    quantity is capped well below the int4 bound the other id fields use. The
    Order total (FR-8) is the sum of price_at_add * quantity over these rows,
    and Order.total_amount is Numeric(10, 2), so an int4-sized quantity would
    overflow that column and raise an unhandled error on an Order nobody could
    then close. 99 is a realistic per-line maximum; a larger order takes a
    second line.
    """

    dish_id: int = Field(gt=0, le=_INT4_MAX)
    quantity: int = Field(gt=0, le=MAX_ORDER_ITEM_QUANTITY)
    notes: str | None = None


class UpdateOrderItemRequest(BaseModel):
    """Body of a Waiter's request to edit a pending Order Item's quantity and/or note.

    Not a partial PATCH like UpdateTableRequest: quantity is always required, there is no
    meaningful "leave quantity alone" partial state the way a Table's number/capacity can be
    edited independently. notes stays optional/nullable exactly like CreateOrderItemRequest's own
    notes field; no reject-explicit-null/at-least-one-field validators are needed here, since the
    frontend always sends both fields and None already means "no note" uniformly on both the add
    and edit paths.
    """

    quantity: int = Field(gt=0, le=MAX_ORDER_ITEM_QUANTITY)
    notes: str | None = None


class OrderItemResponse(BaseModel):
    """Body of any orders endpoint response describing an Order Item."""

    model_config = {"from_attributes": True}

    id: int
    order_id: int
    dish_id: int
    quantity: int
    status: OrderItemStatus
    notes: str | None
    cook_id: int | None
    price_at_add: Decimal


class KitchenItemResponse(BaseModel):
    """Body of GET /api/kitchen/items, describing one active Order Item plus its Table (Story 5.1).

    OrderItemResponse's exact field set plus table_id. table_id is not a column on OrderItem
    itself (only order_id is), so this is not from_attributes-constructible off a bare OrderItem
    the way OrderItemResponse is; KitchenService builds instances explicitly from a (OrderItem,
    table_id) row pair, the one join in this codebase's services/ layer this story explicitly
    justifies (see the story's Scope note) — the Kitchen Display groups by Table, and no existing
    endpoint maps an arbitrary order_id to its table_id for a Cook session.
    """

    id: int
    order_id: int
    table_id: int
    dish_id: int
    quantity: int
    status: OrderItemStatus
    notes: str | None
    cook_id: int | None
    price_at_add: Decimal

    @classmethod
    def from_item(cls, item: "OrderItem", table_id: int) -> "KitchenItemResponse":
        """Build a response from an OrderItem row plus its resolved table_id.

        Args:
            item: The Order Item row.
            table_id: The table_id of the Order this item belongs to.

        Returns:
            The assembled response.
        """
        return cls(
            id=item.id,
            order_id=item.order_id,
            table_id=table_id,
            dish_id=item.dish_id,
            quantity=item.quantity,
            status=item.status,
            notes=item.notes,
            cook_id=item.cook_id,
            price_at_add=item.price_at_add,
        )
