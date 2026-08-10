"""Add case-insensitive unique index on username

Revision ID: f1743862f1b1
Revises: 8c7084cec0ff
Create Date: 2026-08-10 20:24:05.951653

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1743862f1b1'
down_revision: Union[str, Sequence[str], None] = '8c7084cec0ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "uq_users_username_lower"


def upgrade() -> None:
    """Upgrade schema.

    Adds a functional unique index so two usernames differing only by case
    cannot coexist. The plain UNIQUE constraint on the column stays: it is
    what the ORM model declares, and this index is strictly stronger rather
    than a replacement.

    Not created CONCURRENTLY, since Alembic runs each revision inside a
    transaction and the table is small.

    Note: this fails if two existing rows already differ only by username
    case. That is correct, those rows are the ambiguity being closed, and
    they have to be reconciled by hand before upgrading.
    """
    op.create_index(
        INDEX_NAME,
        "users",
        [sa.text("lower(username)")],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema.

    Drops the case-insensitive unique index, returning username uniqueness
    to the column's own case-sensitive UNIQUE constraint.
    """
    op.drop_index(INDEX_NAME, table_name="users")
