"""add is_active to ingredients

Revision ID: c763705514f9
Revises: ff8b89322b7c
Create Date: 2026-08-27 22:03:12.831309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c763705514f9'
down_revision: Union[str, Sequence[str], None] = 'ff8b89322b7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Adds Ingredient.is_active (soft-deactivate, mirrors User.is_active), defaulting every
    existing row to True. Same shape as 819cce996301's price_at_add: added with a temporary
    server_default, then dropped, rather than bare NOT NULL, since a downgrade/upgrade cycle
    (entrypoint.sh runs `alembic upgrade head` on every container start) would otherwise fail a
    NOT NULL violation once real rows exist. Dropping the default afterwards keeps the ORM's own
    `default=True` the only thing that decides this value for a new row, matching
    Ingredient.is_active's mapped_column default.
    """
    op.add_column(
        'ingredients',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column('ingredients', 'is_active', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ingredients', 'is_active')
