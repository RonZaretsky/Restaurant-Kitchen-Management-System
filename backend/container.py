import sys
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass

from dependency_injector import containers, providers
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from clients.websocket import ConnectionRegistry
from services.auth_service import AuthService
from services.inventory_service import InventoryService
from services.realtime_service import RealtimeService
from services.user_service import UserService


@dataclass
class Database:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


def _init_logging(level: str, colorize: bool, format: str) -> Generator:
    logger.remove()
    logger.add(sys.stdout, colorize=colorize, level=level.upper(), format=format)
    yield logger
    logger.remove()


async def _init_database(host: str, port: int, user: str, password: str, name: str) -> AsyncGenerator[Database, None]:
    url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield Database(engine=engine, session_factory=factory)
    await engine.dispose()


async def _init_connection_registry(logger) -> AsyncGenerator[ConnectionRegistry, None]:
    registry = ConnectionRegistry(logger=logger)
    yield registry
    await registry.close_all()


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    logging = providers.Resource(
        _init_logging,
        level=config.logging.level,
        colorize=config.logging.colorize,
        format=config.logging.format,
    )

    database = providers.Resource(
        _init_database,
        host=config.database.host,
        port=config.database.port,
        user=config.database.user,
        password=config.database.password,
        name=config.database.name,
    )

    auth_service = providers.Factory(
        AuthService,
        secret_key=config.auth.secret_key,
        token_expiry_hours=config.auth.token_expiry_hours,
        logger=logging,
    )

    user_service = providers.Factory(
        UserService,
        logger=logging,
    )

    inventory_service = providers.Factory(
        InventoryService,
        logger=logging,
    )

    connection_registry = providers.Resource(_init_connection_registry, logger=logging)

    realtime_service = providers.Factory(
        RealtimeService,
        registry=connection_registry,
        logger=logging,
    )
