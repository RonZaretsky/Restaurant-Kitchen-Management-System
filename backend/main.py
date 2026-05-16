import uvicorn
from fastapi import FastAPI

from constants import SETTINGS
from container import Container
from api.router import router

container = Container()
container.config.from_yaml(SETTINGS.CONFIG_PATH)
container.init_resources()


def create_app() -> FastAPI:
    app = FastAPI(title=SETTINGS.APP_NAME, version=SETTINGS.APP_VERSION, debug=container.config.app.debug())
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
