from collections.abc import Sequence
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import AIRecipeSuggestion, AIRecipeSuggestionResponse, CreateRecipeSuggestionRequest, User, UserRole
from services.ai_service import AIService

router = APIRouter(prefix="/api/smart-chef", tags=["smart-chef"])

# Generating a suggestion is Cook-only (FR-18's own "As a Cook"), no Admin fallback.
SmartChefWriteDep = Annotated[User, Depends(require_role(UserRole.cook))]

# Listing is shared with Story 6.2's Admin review page (same underlying data, Role-level
# permissions per AD-9 — see AIService.list_suggestions's own docstring).
SmartChefReadDep = Annotated[User, Depends(require_role(UserRole.cook, UserRole.admin))]

_ERROR_DESCRIPTIONS = {
    401: "No valid session cookie was supplied",
    403: "Authenticated, but the caller's Role is not permitted for this action",
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
) -> AIRecipeSuggestion:
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
) -> Sequence[AIRecipeSuggestion]:
    """List every Recipe Suggestion, newest first (AC6).

    Args:
        actor: The authenticated Cook or Admin making the request.
        db: The active database session.
        ai_service: Injected service handling the read.

    Returns:
        Every Recipe Suggestion. An empty list is a valid, successful response, not a 404.
    """
    return await ai_service.list_suggestions(db, actor)
