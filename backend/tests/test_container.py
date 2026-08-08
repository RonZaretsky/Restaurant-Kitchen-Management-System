import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from conftest import build_database_url
from constants import SETTINGS
from container import Container
from utils import load_config


async def count_public_tables(database_name: str) -> int:
    engine = create_async_engine(build_database_url(database_name))
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            return result.scalar_one()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_startup_does_not_create_the_schema(empty_database: str) -> None:
    # Arrange
    config = load_config(SETTINGS.CONFIG_PATH)
    config["database"]["name"] = empty_database
    container = Container()
    container.config.from_dict(config)

    # Act
    await container.init_resources()
    try:
        table_count = await count_public_tables(empty_database)
    finally:
        await container.shutdown_resources()

    # Assert
    # This is the guard for AD-4. If create_all is reintroduced, or an alembic
    # upgrade is dropped into the FastAPI lifespan, this fails.
    assert table_count == 0


@pytest.mark.asyncio
async def test_database_resource_exposes_engine_and_session_factory(
    empty_database: str,
) -> None:
    # Arrange
    config = load_config(SETTINGS.CONFIG_PATH)
    config["database"]["name"] = empty_database
    container = Container()
    container.config.from_dict(config)

    # Act
    await container.init_resources()
    try:
        # database is an async resource provider, so calling it returns an
        # awaitable rather than the Database instance itself.
        database = await container.database()
        async with database.session_factory() as session:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar_one()
    finally:
        await container.shutdown_resources()

    # Assert
    assert database.engine is not None
    assert value == 1
