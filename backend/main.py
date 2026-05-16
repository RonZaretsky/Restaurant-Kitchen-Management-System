import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI

from constants import SETTINGS
from container import Container
from api.router import router

_ENV_PATTERN = re.compile(r'\$\{(\w+):\s*([^}]*)\}')


def _load_config(path: Path) -> dict:
    content = path.read_text()
    content = _ENV_PATTERN.sub(
        lambda m: os.environ.get(m.group(1), m.group(2).strip()),
        content,
    )
    return yaml.safe_load(content)


container = Container()
container.config.from_dict(_load_config(SETTINGS.CONFIG_PATH))


@asynccontextmanager
async def lifespan(app: FastAPI):
    container.init_resources()
    yield
    container.shutdown_resources()


def create_app() -> FastAPI:
    app = FastAPI(
        title=SETTINGS.APP_NAME,
        version=SETTINGS.APP_VERSION,
        debug=container.config.app.debug(),
        lifespan=lifespan,
    )
    app.container = container
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
