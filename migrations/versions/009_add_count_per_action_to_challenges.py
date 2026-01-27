"""add count_per_action to challenges

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    # Add count_per_action column to challenges table
    # If set, each action counts as this value regardless of the action's quantity
    op.add_column('challenges', sa.Column('count_per_action', sa.Integer(), nullable=True), schema='new_stability')


def downgrade():
    # Remove count_per_action column from challenges table
    op.drop_column('challenges', 'count_per_action', schema='new_stability')
