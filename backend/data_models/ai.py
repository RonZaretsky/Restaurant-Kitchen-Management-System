import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
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
    """Body of any smart-chef endpoint response describing a Recipe Suggestion."""

    model_config = {"from_attributes": True}

    id: int
    requested_by: int
    prompt_used: str
    generated_recipe: dict[str, Any]
    ingredients_snapshot: list[dict[str, Any]]
    created_at: datetime
