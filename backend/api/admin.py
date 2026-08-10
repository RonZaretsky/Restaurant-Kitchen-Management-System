from collections.abc import Sequence
from typing import Annotated, Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from api.dependencies import require_role
from clients.database import SessionDep
from container import Container
from data_models import (
    CreateUserRequest,
    ErrorResponse,
    ResetPasswordRequest,
    UpdateUserRequest,
    User,
    UserRole,
    UserResponse,
)
from services.user_service import UserService

router = APIRouter(prefix="/api/admin", tags=["admin"])

# The one shared gate for every route in this file: authenticated (via
# CurrentUserDep, layered inside require_role) and Role == admin.
AdminDep = Annotated[User, Depends(require_role(UserRole.admin))]


def _errors(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """Build the OpenAPI `responses` entries for the given error statuses.

    Settles the gap Story 1.2 deferred here. The exceptions these routes raise
    are plain Exception subclasses rather than HTTPException, so FastAPI cannot
    infer any of them and a route would otherwise document only its success
    case. Each entry carries ErrorResponse as its body schema, so a generated
    client sees the `detail` contract and not just a status number.

    Args:
        statuses: The HTTP status codes this route can return as errors.

    Returns:
        A responses mapping ready to pass to a route decorator.
    """
    return {
        status: {"description": _ERROR_DESCRIPTIONS[status], "model": ErrorResponse}
        for status in statuses
    }


_ERROR_DESCRIPTIONS = {
    401: "No valid session cookie was supplied",
    403: "Authenticated, but the caller's Role is not admin",
    404: "No User matches the given id",
    409: "The request conflicts with existing state",
}


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=201,
    responses=_errors(401, 403, 409),
)
@inject
async def create_user(
    payload: CreateUserRequest,
    actor: AdminDep,
    db: SessionDep,
    user_service: UserService = Depends(Provide[Container.user_service]),
) -> User:
    """Create a new User account with an Admin-assigned initial password.

    Args:
        payload: The submitted username, full name, role, and password.
        actor: The authenticated Admin making the request.
        db: The active database session.
        user_service: Injected service handling account creation.

    Returns:
        The newly created User.

    Raises:
        DuplicateUsernameError: Propagated from user_service, handled
            globally as a 409, if the username already exists.
    """
    return await user_service.create_user(db, actor, payload)


@router.get("/users", response_model=list[UserResponse], responses=_errors(401, 403))
@inject
async def list_users(
    actor: AdminDep,
    db: SessionDep,
    user_service: UserService = Depends(Provide[Container.user_service]),
) -> Sequence[User]:
    """List every User account, active and deactivated alike.

    Args:
        actor: The authenticated Admin making the request.
        db: The active database session.
        user_service: Injected service handling the lookup.

    Returns:
        Every User account.
    """
    return await user_service.list_users(db)


@router.get("/users/{user_id}", response_model=UserResponse, responses=_errors(401, 403, 404))
@inject
async def get_user(
    user_id: int,
    actor: AdminDep,
    db: SessionDep,
    user_service: UserService = Depends(Provide[Container.user_service]),
) -> User:
    """Fetch a single User account by id.

    Args:
        user_id: The id of the User to fetch.
        actor: The authenticated Admin making the request.
        db: The active database session.
        user_service: Injected service handling the lookup.

    Returns:
        The matching User.

    Raises:
        UserNotFoundError: Propagated from user_service, handled globally as
            a 404, if no User matches user_id.
    """
    return await user_service.get_user(db, actor, user_id)


@router.patch(
    "/users/{user_id}", response_model=UserResponse, responses=_errors(401, 403, 404, 409)
)
@inject
async def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    actor: AdminDep,
    db: SessionDep,
    user_service: UserService = Depends(Provide[Container.user_service]),
) -> User:
    """Edit a User's full name and/or Role.

    Args:
        user_id: The id of the User to edit.
        payload: The fields to change.
        actor: The authenticated Admin making the request.
        db: The active database session.
        user_service: Injected service handling the edit.

    Returns:
        The updated User.

    Raises:
        UserNotFoundError: Propagated from user_service, handled globally as
            a 404, if no User matches user_id.
        LastAdminLockoutError: Propagated from user_service, handled
            globally as a 409, if the edit would demote the last active
            Admin.
    """
    return await user_service.update_user(db, actor, user_id, payload)


@router.post(
    "/users/{user_id}/deactivate",
    response_model=UserResponse,
    responses=_errors(401, 403, 404, 409),
)
@inject
async def deactivate_user(
    user_id: int,
    actor: AdminDep,
    db: SessionDep,
    user_service: UserService = Depends(Provide[Container.user_service]),
) -> User:
    """Deactivate an active User, blocking further logins.

    Args:
        user_id: The id of the User to deactivate.
        actor: The authenticated Admin making the request.
        db: The active database session.
        user_service: Injected service handling the deactivation.

    Returns:
        The deactivated User.

    Raises:
        UserNotFoundError: Propagated from user_service, handled globally as
            a 404, if no User matches user_id.
        LastAdminLockoutError: Propagated from user_service, handled
            globally as a 409, if this User is the last active Admin.
    """
    return await user_service.deactivate_user(db, actor, user_id)


@router.post(
    "/users/{user_id}/reactivate",
    response_model=UserResponse,
    responses=_errors(401, 403, 404),
)
@inject
async def reactivate_user(
    user_id: int,
    actor: AdminDep,
    db: SessionDep,
    user_service: UserService = Depends(Provide[Container.user_service]),
) -> User:
    """Reactivate a previously deactivated User, restoring their login.

    Args:
        user_id: The id of the User to reactivate.
        actor: The authenticated Admin making the request.
        db: The active database session.
        user_service: Injected service handling the reactivation.

    Returns:
        The reactivated User.

    Raises:
        UserNotFoundError: Propagated from user_service, handled globally as
            a 404, if no User matches user_id.
    """
    return await user_service.reactivate_user(db, actor, user_id)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=UserResponse,
    responses=_errors(401, 403, 404),
)
@inject
async def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    actor: AdminDep,
    db: SessionDep,
    user_service: UserService = Depends(Provide[Container.user_service]),
) -> User:
    """Set a new password on an existing User.

    Never requires or reveals the account's previous password (AC8).

    Args:
        user_id: The id of the User whose password is being reset.
        payload: The new plaintext password. Never logged.
        actor: The authenticated Admin making the request.
        db: The active database session.
        user_service: Injected service handling the reset.

    Returns:
        The updated User.

    Raises:
        UserNotFoundError: Propagated from user_service, handled globally as
            a 404, if no User matches user_id.
    """
    return await user_service.reset_password(db, actor, user_id, payload.new_password)
