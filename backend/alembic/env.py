"""Alembic environment for the Restaurant Kitchen Management System.

The database URL is never stored in alembic.ini. It is rebuilt here from the same
config.yaml values the application uses, so migrations and the app always agree on
which database they are talking to.
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Ordering matters: backend/ has to be importable before the application modules
# below can be loaded. alembic.ini only prepends the current working directory,
# which is wrong whenever alembic runs from anywhere other than backend/.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from constants import SETTINGS
from data_models import Base
from utils import load_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Build the async database URL from the application config.

    Reads config.yaml through utils.load_config, so the ${ENV_VAR: default}
    placeholders resolve the same way they do for the running app. This is what
    makes migrations work both on a developer machine and inside Docker, where
    DB_HOST is "postgres" rather than "localhost".

    Returns:
        A postgresql+asyncpg connection URL.
    """
    settings = load_config(SETTINGS.CONFIG_PATH)
    database = settings["database"]
    return (
        f"postgresql+asyncpg://{database['user']}:{database['password']}"
        f"@{database['host']}:{database['port']}/{database['name']}"
    )


def run_migrations_offline() -> None:
    """Emit migrations as SQL without connecting to a database.

    Used by `alembic upgrade --sql`. Configures the context with a URL only, so
    no DBAPI driver is needed.

    Returns:
        Nothing.
    """
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run the migration scripts against an open connection.

    Args:
        connection: A synchronous-facing connection handed over by run_sync.

    Returns:
        Nothing.
    """
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Open an async engine and run the migrations through it.

    Returns:
        Nothing.
    """
    connectable = create_async_engine(get_database_url(), poolclass=pool.NullPool)

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against a live database.

    Returns:
        Nothing.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
