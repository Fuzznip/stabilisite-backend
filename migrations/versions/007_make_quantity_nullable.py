"""add value to challenges

Revision ID: c8d4f2a7b3e9
Revises: b72f3e9a8c41
Create Date: 2026-01-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8d4f2a7b3e1'
down_revision = 'c8d4f2a7b3e9'
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
