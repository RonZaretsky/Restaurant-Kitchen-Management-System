import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ChatRole(enum.Enum):
    user = "user"
    assistant = "assistant"


class AIRecipeSuggestion(Base):
    __tablename__ = "ai_recipe_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requested_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    prompt_used: Mapped[str] = mapped_column(Text, nullable=False)
    generated_recipe: Mapped[dict] = mapped_column(JSON, nullable=False)
    ingredients_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # Story 6.2, AC4: whether an Admin has dismissed this suggestion. "Confirmed" is deliberately
    # NOT a column here — it is derived from whether any Dish references this suggestion's id
    # (Dish.source_suggestion_id), the same "derived, not stored" pattern Order.status/Low-Stock
    # Alerts already established elsewhere in this codebase.
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AIChatSession(Base):
    __tablename__ = "ai_chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AIChatMessage(Base):
    __tablename__ = "ai_chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_chat_sessions.id"), nullable=False)
    role: Mapped[ChatRole] = mapped_column(Enum(ChatRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CreateRecipeSuggestionRequest(BaseModel):
    """Body of a Cook's request to generate a Recipe Suggestion (Story 6.1, FR-18).

    `direction` steers the suggestion but never overrides the stock-availability constraint, and
    is folded into the persisted `prompt_used` rather than stored as its own field (AC2).
    """

    direction: str | None = None


class AIRecipeSuggestionResponse(BaseModel):
    """Body of any smart-chef endpoint response describing a Recipe Suggestion.

    `confirmed_dish_id` is not an attribute on `AIRecipeSuggestion` itself (there is no stored
    "confirmed" state, see the ORM class's own docstring) — it is resolved by the caller via a
    join against `Dish.source_suggestion_id` and passed to `from_row`, never derived from a bare
    `.model_validate(suggestion)` call the way every other response in this codebase works.
    """

    model_config = {"from_attributes": True}

    id: int
    requested_by: int
    prompt_used: str
    generated_recipe: dict[str, Any]
    ingredients_snapshot: list[dict[str, Any]]
    created_at: datetime
    dismissed: bool
    confirmed_dish_id: int | None

    @classmethod
    def from_row(cls, suggestion: "AIRecipeSuggestion", confirmed_dish_id: int | None) -> "AIRecipeSuggestionResponse":
        """Build a response from a Recipe Suggestion row plus its resolved confirmed-Dish id.

        Args:
            suggestion: The Recipe Suggestion row.
            confirmed_dish_id: The id of the Dish that cites this suggestion as its source, or
                None if no such Dish exists yet.

        Returns:
            The assembled response.
        """
        return cls(
            id=suggestion.id,
            requested_by=suggestion.requested_by,
            prompt_used=suggestion.prompt_used,
            generated_recipe=suggestion.generated_recipe,
            ingredients_snapshot=suggestion.ingredients_snapshot,
            created_at=suggestion.created_at,
            dismissed=suggestion.dismissed,
            confirmed_dish_id=confirmed_dish_id,
        )
