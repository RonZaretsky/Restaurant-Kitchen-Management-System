from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import func, select

from clients.database import session_scope
from constants import SETTINGS
from container import Container
from data_models import User, UserRole
from exceptions.handlers import register_exception_handlers
from services.auth_service import AuthService
from utils import load_config
from api.router import router

DEFAULT_SECRET_KEY = "dev-only-insecure-secret-change-me"

# Fresh-clone bootstrap only (see _bootstrap_first_admin): a fixed, published default, not a
# secret. Meant to be changed immediately via the Users screen once logged in.
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"

container = Container()
container.config.from_dict(load_config(SETTINGS.CONFIG_PATH))

# Every later story that adds @inject to a new module appends its name here,
# never replaces the list (AD-1).
container.wire(
    modules=[
        "api.auth",
        "api.dependencies",
        "api.admin",
        "api.websocket",
        "api.inventory",
        "api.menu",
        "api.tables",
        "api.orders",
        "api.kitchen",
        "api.smart_chef",
    ]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await container.init_resources()
    _warn_if_default_secret_key()
    _warn_if_no_openai_key()
    if container.config.app.bootstrap_admin():
        await _bootstrap_first_admin(app)
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


def _warn_if_no_openai_key() -> None:
    """Log a warning if OPENAI_API_KEY is unset (Story 6.1).

    Unlike JWT_SECRET_KEY there is no functional fallback to warn about
    silently accepting: a missing key just means every Smart Chef call fails
    at request time. Deliberately a warning rather than a hard failure,
    mirroring _warn_if_default_secret_key, so a fresh clone with no OpenAI
    key configured still starts for the rest of the app to be demoed.

    Returns:
        Nothing.
    """
    if not container.config.smart_chef.api_key():
        logger.warning(
            "OPENAI_API_KEY is not set. Smart Chef calls will fail. "
            "Set it in backend/.env (see backend/.env.example)."
        )


async def _bootstrap_first_admin(app: FastAPI) -> None:
    """Create a default Admin account if the `users` table is empty.

    Every route requires an authenticated Admin (Story 1.6+), and there is no other way to
    reach a fresh clone: `docker compose up` alone would otherwise leave no way to log in.
    Checked on every startup, not just the first: idempotent via the row count, so it never
    creates a second account once any User exists (including one added by hand or since
    deactivated). Disabled during tests via `BOOTSTRAP_ADMIN=false` (see tests/conftest.py) so
    the empty-`users`-table assumption every other test relies on still holds.

    Args:
        app: The FastAPI app, read for its DI container (matches session_scope's own contract).

    Returns:
        Nothing.
    """
    async with session_scope(app) as db:
        user_count = await db.execute(select(func.count()).select_from(User))
        if user_count.scalar_one() > 0:
            return

        admin = User(
            username=DEFAULT_ADMIN_USERNAME,
            password_hash=AuthService.hash_password(DEFAULT_ADMIN_PASSWORD),
            full_name="Default Admin",
            role=UserRole.admin,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        logger.warning(
            "No Users found - created a default Admin (username={}, password={}). "
            "Change this password immediately from the Users screen.",
            DEFAULT_ADMIN_USERNAME,
            DEFAULT_ADMIN_PASSWORD,
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
