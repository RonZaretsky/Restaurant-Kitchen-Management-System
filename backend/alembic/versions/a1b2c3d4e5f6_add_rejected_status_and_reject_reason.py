"""add rejected status and reject_reason to order_items

Revision ID: a1b2c3d4e5f6
Revises: c763705514f9
Create Date: 2026-08-28 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c763705514f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the rejected value to orderitemstatus, plus OrderItem.reject_reason.

    Autogenerate cannot see enum value additions, the ADD VALUE line has to be written by hand
    (same as 856ef9ffb5cd's own "add cancelled" precedent). Safe to run inside Alembic's
    transactional DDL on Postgres 12+, as long as the new value is not used in the same
    transaction, which it is not here — the reject_reason column addition alongside it is
    unrelated DDL, not a use of the new enum value.
    """
    op.execute("ALTER TYPE orderitemstatus ADD VALUE 'rejected'")
    op.add_column("order_items", sa.Column("reject_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    """Refuse to downgrade past this revision.

    Postgres has no clean way to remove a value from an existing enum type. A real downgrade
    would require a manual data migration for any row already carrying 'rejected', not something
    this migration can safely automate (same reasoning as 856ef9ffb5cd's own downgrade refusal).
    """
    raise NotImplementedError(
        "Postgres cannot cleanly remove an enum value; downgrading past this revision "
        "requires a manual data migration for any row already using 'rejected'."
    )
