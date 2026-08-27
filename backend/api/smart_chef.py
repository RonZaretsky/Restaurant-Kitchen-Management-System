from collections.abc import Sequence
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import (
    AIChatMessageResponse,
    AIChatSessionResponse,
    AIRecipeSuggestionResponse,
    CreateChatMessageRequest,
    CreateChatSessionRequest,
    CreateRecipeSuggestionRequest,
    User,
    UserRole,
)
from data_models.menu import _INT4_MAX
from services.ai_service import AIService

router = APIRouter(prefix="/api/smart-chef", tags=["smart-chef"])

# Generating a suggestion is Cook-only (FR-18's own "As a Cook"), no Admin fallback.
SmartChefWriteDep = Annotated[User, Depends(require_role(UserRole.cook))]

# Listing is shared with Story 6.2's Admin review page (same underlying data, Role-level
# permissions per AD-9 — see AIService.list_suggestions's own docstring).
SmartChefReadDep = Annotated[User, Depends(require_role(UserRole.cook, UserRole.admin))]

# Dismissing is Admin-only (Story 6.2, UX-DR20) — narrower than SmartChefReadDep, no Cook access.
SmartChefAdminDep = Annotated[User, Depends(require_role(UserRole.admin))]

SuggestionIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]
SessionIdPath = Annotated[int, Path(gt=0, le=_INT4_MAX)]

_ERROR_DESCRIPTIONS = {
    401: "No valid session cookie was supplied",
    403: "Authenticated, but the caller's Role is not permitted for this action",
    404: "No matching Recipe Suggestion was found",
    409: "A suggestion is already generating for this Cook",
    502: "The OpenAI call failed, timed out, or returned unparseable content",
}

_GENERATE_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: "Authenticated, but the caller's Role is not cook",
    409: _ERROR_DESCRIPTIONS[409],
    502: _ERROR_DESCRIPTIONS[502],
}

_LIST_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: "Authenticated, but the caller's Role is not cook or admin",
}

_DISMISS_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: "Authenticated, but the caller's Role is not admin",
    404: _ERROR_DESCRIPTIONS[404],
    409: "The suggestion is already dismissed or already confirmed",
}

_CREATE_CHAT_SESSION_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: "Authenticated, but the caller's Role is not cook",
    404: "No matching Dish or Recipe Suggestion was found",
}

_LIST_CHAT_SESSIONS_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: "Authenticated, but the caller's Role is not cook or admin",
}

_LIST_CHAT_MESSAGES_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: "Authenticated, but the caller's Role is not cook or admin",
    404: "No matching Chat Session was found",
}

_SEND_CHAT_MESSAGE_ERROR_DESCRIPTIONS = {
    401: _ERROR_DESCRIPTIONS[401],
    403: "Authenticated, but the caller's Role is not cook",
    404: "No matching Chat Session was found",
    409: "A reply is already generating for this session",
    502: "The OpenAI call failed, timed out, or returned unusable content",
}


@router.post(
    "/suggestions",
    response_model=AIRecipeSuggestionResponse,
    status_code=201,
    responses=error_responses(_GENERATE_ERROR_DESCRIPTIONS, 401, 403, 409, 502),
)
@inject
async def generate_suggestion(
    payload: CreateRecipeSuggestionRequest,
    actor: SmartChefWriteDep,
    db: SessionDep,
    ai_service: AIService = Depends(Provide[Container.ai_service]),
) -> AIRecipeSuggestionResponse:
    """Generate and persist a Recipe Suggestion from current stock (AC1, AC2).

    Args:
        payload: The optional free-text direction.
        actor: The authenticated Cook making the request.
        db: The active database session.
        ai_service: Injected service handling the generation.

    Returns:
        The newly created Recipe Suggestion.

    Raises:
        SuggestionGenerationInProgressError: Propagated from ai_service, handled globally as a
            409, if a generation is already in flight for this Cook (AC3).
        AIGenerationFailedError: Propagated from ai_service, handled globally as a 502, if the
            OpenAI call fails, times out, or returns unparseable content (AC4).
    """
    return await ai_service.generate_suggestion(db, actor, payload.direction)


@router.get(
    "/suggestions",
    response_model=list[AIRecipeSuggestionResponse],
    responses=error_responses(_LIST_ERROR_DESCRIPTIONS, 401, 403),
)
@inject
async def list_suggestions(
    actor: SmartChefReadDep,
    db: SessionDep,
    ai_service: AIService = Depends(Provide[Container.ai_service]),
) -> Sequence[AIRecipeSuggestionResponse]:
    """List every Recipe Suggestion, newest first (AC6).

    Args:
        actor: The authenticated Cook or Admin making the request.
        db: The active database session.
        ai_service: Injected service handling the read.

    Returns:
        Every Recipe Suggestion. An empty list is a valid, successful response, not a 404.
    """
    return await ai_service.list_suggestions(db, actor)


@router.post(
    "/suggestions/{suggestion_id}/dismiss",
    response_model=AIRecipeSuggestionResponse,
    responses=error_responses(_DISMISS_ERROR_DESCRIPTIONS, 401, 403, 404, 409),
)
@inject
async def dismiss_suggestion(
    suggestion_id: SuggestionIdPath,
    actor: SmartChefAdminDep,
    db: SessionDep,
    ai_service: AIService = Depends(Provide[Container.ai_service]),
) -> AIRecipeSuggestionResponse:
    """Dismiss a Recipe Suggestion, retaining it for audit (AC4).

    Args:
        suggestion_id: The id of the Recipe Suggestion to dismiss.
        actor: The authenticated Admin making the request.
        db: The active database session.
        ai_service: Injected service handling the dismiss.

    Returns:
        The now-dismissed Recipe Suggestion.

    Raises:
        SuggestionNotFoundError: Propagated from ai_service, handled globally as a 404, if no
            Recipe Suggestion matches suggestion_id.
        SuggestionAlreadyDismissedError: Propagated from ai_service, handled globally as a 409,
            if the suggestion is already dismissed.
        SuggestionAlreadyConfirmedError: Propagated from ai_service, handled globally as a 409,
            if a Dish already cites this suggestion as its source.
    """
    return await ai_service.dismiss_suggestion(db, actor, suggestion_id)


@router.post(
    "/chat-sessions",
    response_model=AIChatSessionResponse,
    status_code=201,
    responses=error_responses(_CREATE_CHAT_SESSION_ERROR_DESCRIPTIONS, 401, 403, 404),
)
@inject
async def create_chat_session(
    payload: CreateChatSessionRequest,
    actor: SmartChefWriteDep,
    db: SessionDep,
    ai_service: AIService = Depends(Provide[Container.ai_service]),
) -> AIChatSessionResponse:
    """Open a new Chat Session tied to a Dish or a Recipe Suggestion (Story 6.3, AC1).

    Args:
        payload: The Dish or Recipe Suggestion this session targets (exactly one, enforced by
            the request schema's own validator).
        actor: The authenticated Cook making the request.
        db: The active database session.
        ai_service: Injected service handling the creation.

    Returns:
        The newly created Chat Session.

    Raises:
        DishNotFoundError: Propagated from ai_service, handled globally as a 404, if dish_id is
            set but no matching Dish exists.
        SuggestionNotFoundError: Propagated from ai_service, handled globally as a 404, if
            suggestion_id is set but no matching Recipe Suggestion exists.
    """
    return await ai_service.create_chat_session(db, actor, payload.dish_id, payload.suggestion_id)


@router.get(
    "/chat-sessions",
    response_model=list[AIChatSessionResponse],
    responses=error_responses(_LIST_CHAT_SESSIONS_ERROR_DESCRIPTIONS, 401, 403),
)
@inject
async def list_chat_sessions(
    actor: SmartChefReadDep,
    db: SessionDep,
    ai_service: AIService = Depends(Provide[Container.ai_service]),
) -> Sequence[AIChatSessionResponse]:
    """List every Chat Session, newest first (AC3, AC6).

    Args:
        actor: The authenticated Cook or Admin making the request.
        db: The active database session.
        ai_service: Injected service handling the read.

    Returns:
        Every Chat Session. An empty list is a valid, successful response, not a 404.
    """
    return await ai_service.list_chat_sessions(db, actor)


@router.get(
    "/chat-sessions/{session_id}/messages",
    response_model=list[AIChatMessageResponse],
    responses=error_responses(_LIST_CHAT_MESSAGES_ERROR_DESCRIPTIONS, 401, 403, 404),
)
@inject
async def list_chat_messages(
    session_id: SessionIdPath,
    actor: SmartChefReadDep,
    db: SessionDep,
    ai_service: AIService = Depends(Provide[Container.ai_service]),
) -> Sequence[AIChatMessageResponse]:
    """List every Message in a Chat Session, oldest first (AC1, AC5).

    Args:
        session_id: The Chat Session whose messages are being listed.
        actor: The authenticated Cook or Admin making the request.
        db: The active database session.
        ai_service: Injected service handling the read.

    Returns:
        Every Message in the session, in chronological order.

    Raises:
        ChatSessionNotFoundError: Propagated from ai_service, handled globally as a 404, if no
            Chat Session matches session_id.
    """
    return await ai_service.list_chat_messages(db, actor, session_id)


@router.post(
    "/chat-sessions/{session_id}/messages",
    response_model=list[AIChatMessageResponse],
    status_code=201,
    responses=error_responses(_SEND_CHAT_MESSAGE_ERROR_DESCRIPTIONS, 401, 403, 404, 409, 502),
)
@inject
async def send_chat_message(
    session_id: SessionIdPath,
    payload: CreateChatMessageRequest,
    actor: SmartChefWriteDep,
    db: SessionDep,
    ai_service: AIService = Depends(Provide[Container.ai_service]),
) -> Sequence[AIChatMessageResponse]:
    """Send a message into a Chat Session and persist the assistant's reply (AC1, AC2, AC4, AC5).

    Args:
        session_id: The Chat Session to send into.
        payload: The Cook's message content.
        actor: The authenticated Cook making the request.
        db: The active database session.
        ai_service: Injected service handling the send.

    Returns:
        The two newly persisted Messages, user then assistant.

    Raises:
        ChatSessionNotFoundError: Propagated from ai_service, handled globally as a 404, if no
            Chat Session matches session_id.
        ChatMessageInProgressError: Propagated from ai_service, handled globally as a 409, if a
            reply is already generating for this session (AC3).
        AIChatReplyFailedError: Propagated from ai_service, handled globally as a 502, if the
            OpenAI call fails, times out, or errors (AC4).
    """
    return await ai_service.send_message(db, actor, session_id, payload.content)
