import asyncio
import os

# Ordering matters. main.py reads config.yaml at import time, so the test database
# name has to be in the environment before any application module is imported below.
# Forcing DB_NAME here is what keeps the suite off the development database.
os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME") or "kitchen_test"

# The client fixture below runs the real app lifespan (app.router.lifespan_context), which would
# otherwise auto-create a default Admin on every test's empty database — silently breaking every
# test that assumes a genuinely empty users table (e.g. AD-15's last-Admin guard tests).
os.environ["BOOTSTRAP_ADMIN"] = "false"

from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from alembic.config import Config
from constants import SETTINGS
from data_models import Base
from main import app
from utils import load_config

BACKEND_ROOT = Path(__file__).resolve().parent.parent
MAINTENANCE_DATABASE = "postgres"


def build_database_url(database_name: str) -> str:
    database = load_config(SETTINGS.CONFIG_PATH)["database"]
    return (
        f"postgresql+asyncpg://{database['user']}:{database['password']}"
        f"@{database['host']}:{database['port']}/{database_name}"
    )


def test_database_name() -> str:
    return load_config(SETTINGS.CONFIG_PATH)["database"]["name"]


def guard_test_database_name(name: str) -> None:
    # A misconfigured TEST_DB_NAME could otherwise resolve to a real database (config.yaml's
    # DB_NAME default is "kitchen", the same name the dev database uses), and this module
    # issues DROP DATABASE against whatever name it's given.
    if not (name.endswith("_test") or name.endswith("_empty")):
        raise RuntimeError(
            f'refusing to drop or create database "{name}": name must end in "_test" or '
            '"_empty" to be treated as a throwaway test database'
        )


async def run_on_maintenance_database(statement: str) -> None:
    # CREATE DATABASE and DROP DATABASE cannot run inside a transaction, hence AUTOCOMMIT.
    engine = create_async_engine(
        build_database_url(MAINTENANCE_DATABASE),
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def truncate_all_tables(engine: AsyncEngine) -> None:
    # Every model table in one statement so foreign keys never block the order.
    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


def run_migrations() -> None:
    # Runs the real upgrade command against the same alembic.ini the deployed container
    # uses, so a broken migration chain fails the suite instead of hiding.
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, "head")


@pytest_asyncio.fixture
async def empty_database() -> AsyncGenerator[str, None]:
    name = f"{test_database_name()}_empty"
    guard_test_database_name(name)
    await run_on_maintenance_database(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    await run_on_maintenance_database(f'CREATE DATABASE "{name}"')
    try:
        yield name
    finally:
        await run_on_maintenance_database(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="session")
def migrated_database() -> Generator[str, None, None]:
    # Building the schema with alembic rather than create_all means every run re-proves
    # the migration chain can raise the schema from nothing.
    name = test_database_name()
    guard_test_database_name(name)
    # Dropped before it is created in case an earlier run died before its own cleanup.
    asyncio.run(run_on_maintenance_database(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    asyncio.run(run_on_maintenance_database(f'CREATE DATABASE "{name}"'))
    run_migrations()

    yield name

    asyncio.run(run_on_maintenance_database(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest_asyncio.fixture
async def db_session(migrated_database: str) -> AsyncGenerator[AsyncSession, None]:
    # Built the same way container.py builds the production session factory, so tests
    # never exercise a second, divergent session configuration.
    engine = create_async_engine(build_database_url(migrated_database), echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as session:
            yield session
        # Rows have to be committed for the app under test to see them over its own
        # connection, so per-test isolation is truncation afterwards rather than a
        # rollback. Without this, writes leak into every later test on the
        # session-scoped database. alembic_version is untouched: it is not a model
        # table, so the migration state survives.
        await truncate_all_tables(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(migrated_database: str) -> AsyncGenerator[AsyncClient, None]:
    # Entering the lifespan initialises and disposes container resources exactly as the
    # app does for real. migrated_database is depended on so the schema exists first.
    # base_url is https (not http): the session cookie is Secure-flagged (AD-3), and
    # unlike a browser, httpx enforces Secure literally with no localhost exemption, so
    # an http base_url would silently drop the cookie on every request after login.
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as http_client:
            yield http_client
