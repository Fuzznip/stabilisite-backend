"""add value to challenges

Revision ID: c8d4f2a7b3e9
Revises: b72f3e9a8c41
Create Date: 2026-01-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8d4f2a7b3e9'
down_revision = 'b72f3e9a8c41'
branch_labels = None
depends_on = None


def upgrade():
    # Add value column to challenges table with default of 1
    op.update('challenges', sa.Column('value', sa.Integer(), nullable=False, server_default='1'), schema='new_stability')


def downgrade():
    # Remove value column from challenges table
    op.drop_column('challenges', 'value', schema='new_stability')
