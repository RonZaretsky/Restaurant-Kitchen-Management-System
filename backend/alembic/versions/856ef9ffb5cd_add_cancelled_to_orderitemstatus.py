"""add cancelled to orderitemstatus

Revision ID: 856ef9ffb5cd
Revises: 819cce996301
Create Date: 2026-08-15 16:27:04.941732

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '856ef9ffb5cd'
down_revision: Union[str, Sequence[str], None] = '819cce996301'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the cancelled value to the orderitemstatus Postgres enum (AD-11).

    Autogenerate cannot see enum value additions, this has to be written by
    hand. Safe to run inside Alembic's transactional DDL on Postgres 12+, as
    long as the new value is not used in the same transaction, which it is
    not here.
    """
    op.execute("ALTER TYPE orderitemstatus ADD VALUE 'cancelled'")


def downgrade() -> None:
    """Refuse to downgrade past this revision.

    Postgres has no clean way to remove a value from an existing enum type.
    A real downgrade would require a manual data migration for any row
    already carrying 'cancelled', not something this migration can safely
    automate.
    """
    raise NotImplementedError(
        "Postgres cannot cleanly remove an enum value; downgrading past this revision "
        "requires a manual data migration for any row already using 'cancelled'."
    )
