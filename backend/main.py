from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from constants import SETTINGS
from container import Container
from exceptions.handlers import register_exception_handlers
from utils import load_config
from api.router import router

DEFAULT_SECRET_KEY = "dev-only-insecure-secret-change-me"

container = Container()
container.config.from_dict(load_config(SETTINGS.CONFIG_PATH))

# Every later story that adds @inject to a new module appends its name here,
# never replaces the list (AD-1).
container.wire(modules=["api.auth", "api.dependencies", "api.admin", "api.websocket", "api.inventory"])


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
    register_exception_handlers(app)
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
