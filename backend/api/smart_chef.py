from collections.abc import Sequence
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path

from api.dependencies import require_role
from api.responses import error_responses
from clients.database import SessionDep
from container import Container
from data_models import AIRecipeSuggestionResponse, CreateRecipeSuggestionRequest, User, UserRole
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
