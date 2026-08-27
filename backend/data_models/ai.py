import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .menu import _INT4_MAX
from .user import _strip_and_require_content


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
    # Story 6.3: exactly one of these two is set per session, enforced by
    # CreateChatSessionRequest's model_validator (application-level, not a DB CHECK constraint,
    # matching this codebase's established pattern for a business-rule invariant). Both nullable,
    # no default and no backfill concern — a session created before this story never existed.
    dish_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("dishes.id"), nullable=True)
    suggestion_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_recipe_suggestions.id"), nullable=True
    )


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


class CreateChatSessionRequest(BaseModel):
    """Body of a Cook's request to open a Chat Session tied to a Dish or a Recipe Suggestion
    (Story 6.3, FR-20).

    Exactly one of `dish_id`/`suggestion_id` must be set — a session with no target or two
    targets is meaningless, rejected here with a 422 rather than reaching the service at all
    (mirrors `UpdateUserRequest.at_least_one_field`'s shape, inverted to "exactly one").
    """

    dish_id: int | None = Field(default=None, gt=0, le=_INT4_MAX)
    suggestion_id: int | None = Field(default=None, gt=0, le=_INT4_MAX)

    @model_validator(mode="after")
    def exactly_one_target(self) -> "CreateChatSessionRequest":
        """Reject a request naming neither or both targets.

        Returns:
            This instance, unchanged, if exactly one target is set.

        Raises:
            ValueError: If both or neither of dish_id/suggestion_id are set.
        """
        if (self.dish_id is None) == (self.suggestion_id is None):
            raise ValueError("exactly one of dish_id or suggestion_id must be provided")
        return self


class AIChatSessionResponse(BaseModel):
    """Body of any smart-chef endpoint response describing a Chat Session.

    Plain `model_validate(session)` is sufficient here (unlike AIRecipeSuggestionResponse):
    nothing about a session is derived from a join.
    """

    model_config = {"from_attributes": True}

    id: int
    user_id: int
    dish_id: int | None
    suggestion_id: int | None
    title: str
    created_at: datetime


class CreateChatMessageRequest(BaseModel):
    """Body of a Cook's request to send a message into an existing Chat Session (Story 6.3, AC1).

    No `max_length` bound — matches `CreateOrderItemRequest.notes`'s already-accepted
    unbounded-free-text precedent (deferred-work.md, Story 3.2 entry), a conscious match, not
    an oversight.
    """

    content: str = Field(min_length=1)

    _strip_content = field_validator("content")(_strip_and_require_content)


class AIChatMessageResponse(BaseModel):
    """Body of any smart-chef endpoint response describing a Chat Message."""

    model_config = {"from_attributes": True}

    id: int
    session_id: int
    role: ChatRole
    content: str
    created_at: datetime
