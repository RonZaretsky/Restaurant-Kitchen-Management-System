from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from constants import SETTINGS
from container import Container
from exceptions import InvalidCredentialsError
from utils import load_config
from api.router import router

container = Container()
container.config.from_dict(load_config(SETTINGS.CONFIG_PATH))

# The first entry in the wire list (AD-1). Every later story that adds
# @inject to a new router module appends its name here, never replaces
# the list.
container.wire(modules=["api.auth"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await container.init_resources()
    yield
    await container.shutdown_resources()


async def _invalid_credentials_handler(request: Request, exc: InvalidCredentialsError) -> JSONResponse:
    """Return the single generic login-failure response for any credential error.

    Args:
        request: The incoming request that triggered the error.
        exc: The raised InvalidCredentialsError. Its details are never used in
            the response, only its type, so the message can never drift
            between call sites.

    Returns:
        A 401 JSON response with a fixed, non-revealing error message.
    """
    return JSONResponse(status_code=401, content={"detail": "Invalid username or password"})


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
    app.add_exception_handler(InvalidCredentialsError, _invalid_credentials_handler)
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
