import sys
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass

from dependency_injector import containers, providers
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from data_models import Base


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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield Database(engine=engine, session_factory=factory)
    await engine.dispose()


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
