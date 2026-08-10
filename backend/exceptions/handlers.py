from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from exceptions import AuthError, ConflictError, ForbiddenError, UserNotFoundError


async def _auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    """Turn any authentication failure into a 401 carrying its own message.

    One handler for the whole AuthError family, so each message stays defined
    in exactly one place and cannot drift between call sites.

    Args:
        request: The incoming request that triggered the error.
        exc: The raised AuthError subclass, whose detail becomes the response
            body.

    Returns:
        A 401 JSON response.
    """
    return JSONResponse(status_code=401, content={"detail": exc.detail})


async def _forbidden_error_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
    """Turn a role-authorization failure into a 403 carrying its message.

    Kept separate from _auth_error_handler: a ForbiddenError means the
    caller's identity is already verified and only their Role lacks
    permission, a distinct case from an AuthError that must stay
    independently testable and never collapse into a 401.

    Args:
        request: The incoming request that triggered the error.
        exc: The raised ForbiddenError, whose detail becomes the response
            body.

    Returns:
        A 403 JSON response.
    """
    return JSONResponse(status_code=403, content={"detail": exc.detail})


async def _conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
    """Turn a business-rule or uniqueness conflict into a 409 carrying its message.

    One handler for the whole ConflictError family (duplicate username,
    last-admin lockout), so each message stays defined in exactly one place.

    Args:
        request: The incoming request that triggered the error.
        exc: The raised ConflictError subclass, whose detail becomes the
            response body.

    Returns:
        A 409 JSON response.
    """
    return JSONResponse(status_code=409, content={"detail": exc.detail})


async def _user_not_found_error_handler(request: Request, exc: UserNotFoundError) -> JSONResponse:
    """Turn a missing-User lookup into a 404 carrying its message.

    Args:
        request: The incoming request that triggered the error.
        exc: The raised UserNotFoundError, whose detail becomes the response
            body.

    Returns:
        A 404 JSON response.
    """
    return JSONResponse(status_code=404, content={"detail": exc.detail})


def register_exception_handlers(app: FastAPI) -> None:
    """Register every domain exception's handler on the given app.

    One call from main.py's composition root, so adding a new exception
    family means adding a handler function here and one line to this list,
    never touching main.py itself.

    Args:
        app: The FastAPI app to register handlers on.

    Returns:
        Nothing.
    """
    app.add_exception_handler(AuthError, _auth_error_handler)
    app.add_exception_handler(ForbiddenError, _forbidden_error_handler)
    app.add_exception_handler(ConflictError, _conflict_error_handler)
    app.add_exception_handler(UserNotFoundError, _user_not_found_error_handler)
