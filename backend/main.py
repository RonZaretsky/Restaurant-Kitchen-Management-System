from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from constants import SETTINGS
from container import Container
from exceptions import AuthError, ConflictError, ForbiddenError, UserNotFoundError
from utils import load_config
from api.router import router

DEFAULT_SECRET_KEY = "dev-only-insecure-secret-change-me"

container = Container()
container.config.from_dict(load_config(SETTINGS.CONFIG_PATH))

# Every later story that adds @inject to a new module appends its name here,
# never replaces the list (AD-1).
container.wire(modules=["api.auth", "api.dependencies", "api.admin"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await container.init_resources()
    _warn_if_default_secret_key()
    yield
    await container.shutdown_resources()


def _warn_if_default_secret_key() -> None:
    """Log a warning if the JWT signing key is still the committed default.

    The default is published in this repository, so anyone can forge a token
    against a deployment still using it. Set JWT_SECRET_KEY in backend/.env.
    Deliberately a warning rather than a hard failure, so a fresh clone still
    starts for the local demo.

    Returns:
        Nothing.
    """
    if container.config.auth.secret_key() == DEFAULT_SECRET_KEY:
        logger.warning(
            "JWT_SECRET_KEY is still the published default. Sessions are forgeable. "
            "Set it in backend/.env (see backend/.env.example)."
        )


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


def create_app() -> FastAPI:
    app = FastAPI(
        title=SETTINGS.APP_NAME,
        version=SETTINGS.APP_VERSION,
        debug=container.config.app.debug(),
        lifespan=lifespan,
    )
    app.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[container.config.cors.allow_origin()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(AuthError, _auth_error_handler)
    app.add_exception_handler(ForbiddenError, _forbidden_error_handler)
    app.add_exception_handler(ConflictError, _conflict_error_handler)
    app.add_exception_handler(UserNotFoundError, _user_not_found_error_handler)
    app.include_router(router)
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=container.config.server.host(),
        port=container.config.server.port(),
        reload=container.config.app.debug(),
    )
