import enum
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MovementType(enum.Enum):
    purchase = "purchase"
    consumption = "consumption"
    waste = "waste"
    adjustment = "adjustment"


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ingredient_id: Mapped[int] = mapped_column(Integer, ForeignKey("ingredients.id"), nullable=False)
    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType), nullable=False)
    quantity_change: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    performed_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CreateStockMovementRequest(BaseModel):
    """Body of a Warehouse Manager's or Admin's request to log a Stock Movement.

    movement_type accepts the full MovementType enum at the field level (no Literal-based
    subset type exists anywhere in this codebase to follow as precedent), but the validator
    below rejects `consumption`: it belongs to the automatic pick-up path only, never a manually
    submitted value here, mirroring `UpdateRecipeIngredientRequest.at_least_one_field`'s
    validator-rejects-the-disallowed-case shape.

    Sign convention: quantity is a plain positive magnitude for purchase/waste
    (the direction is implied by movement_type); for adjustment it is the already-signed
    delta the caller wants applied (positive or negative, never zero).
    """

    movement_type: MovementType
    # max_digits/decimal_places match StockMovement.quantity_change's Numeric(10, 3) column
    # exactly, so an out-of-range value 422s instead of 500ing. No ge/gt bound
    # at the field level: validity depends on
    # movement_type, enforced below.
    quantity: Decimal = Field(max_digits=10, decimal_places=3)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_type_and_quantity(self) -> "CreateStockMovementRequest":
        """Reject consumption, and enforce the sign convention for the other three types.

        Returns:
            This instance, unchanged, if movement_type/quantity are a valid combination.

        Raises:
            ValueError: If movement_type is consumption, if quantity is <= 0 for a
                purchase/waste movement, or if quantity is exactly 0 for an adjustment.
        """
        if self.movement_type == MovementType.consumption:
            raise ValueError("consumption is recorded automatically and cannot be logged manually")
        if self.movement_type in (MovementType.purchase, MovementType.waste) and self.quantity <= 0:
            raise ValueError("quantity must be greater than zero for a purchase or waste movement")
        if self.movement_type == MovementType.adjustment and self.quantity == 0:
            raise ValueError("quantity must not be zero for an adjustment movement")
        return self


class StockMovementResponse(BaseModel):
    """Body of any inventory endpoint response describing a Stock Movement.

    Maps 1:1 to StockMovement's own columns (no joined/enriched data), matching
    OrderItemResponse's precedent of returning raw ids (`performed_by`, like `cook_id`)
    rather than a resolved display name: no endpoint resolves a user id to a name for
    this audience, so the frontend renders `performed_by` as a plain id. A known,
    deliberate gap rather than an oversight.
    """

    model_config = {"from_attributes": True}

    id: int
    ingredient_id: int
    movement_type: MovementType
    quantity_change: Decimal
    reference_id: int | None
    performed_by: int
    timestamp: datetime
    notes: str | None
