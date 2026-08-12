import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from data_models import Base


@pytest.mark.asyncio
async def test_schema_was_built_by_alembic(db_session: AsyncSession) -> None:
    # Act
    result = await db_session.execute(text("SELECT version_num FROM alembic_version"))

    # Assert
    # A populated alembic_version table proves the schema came from the migration
    # chain rather than from a metadata create call.
    assert result.scalar_one()


@pytest.mark.asyncio
async def test_migrations_create_every_model_table(db_session: AsyncSession) -> None:
    # Act
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    )
    existing = set(result.scalars())

    # Assert
    assert set(Base.metadata.tables) <= existing


@pytest.mark.asyncio
async def test_migrations_match_the_models(db_session: AsyncSession) -> None:
    # Arrange
    def _diff(sync_connection: Connection) -> list:
        context = MigrationContext.configure(sync_connection)
        return compare_metadata(context, Base.metadata)

    # Act
    connection = await db_session.connection()
    differences = await connection.run_sync(_diff)

    # Assert
    # Empty means no drift between the migrated schema and the ORM metadata. This is
    # the check that keeps every later story honest: adding a column to a model
    # without shipping a revision makes this fail.
    assert differences == []


def test_every_not_found_error_inherits_the_shared_base():
    # Arrange: one handler is registered against NotFoundError and Starlette
    # dispatches by walking the MRO, so a sibling that forgets to inherit it
    # would become a silent 500 instead of a 404.
    import exceptions

    # Act
    not_found_types = [
        value
        for name, value in vars(exceptions).items()
        if name.endswith("NotFoundError") and isinstance(value, type)
    ]

    # Assert
    assert not_found_types
    for error_type in not_found_types:
        assert issubclass(error_type, exceptions.NotFoundError), error_type.__name__
