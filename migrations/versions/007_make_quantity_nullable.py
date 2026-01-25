"""make quantity nullable

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-01-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
     # Make quantity nullable in challenges table
    op.alter_column(
        'challenges',
        'quantity',
        existing_type=sa.Integer(),
        nullable=True,
        schema='new_stability'
    )


def downgrade():
    # Revert quantity to NOT NULL
    # NOTE: This will fail if any rows have NULL quantity
    op.alter_column(
        'challenges',
        'quantity',
        existing_type=sa.Integer(),
        nullable=False,
        schema='new_stability'
    )
