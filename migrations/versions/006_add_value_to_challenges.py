"""add value to challenges

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-01-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    # Add value column to challenges table with default of 1
    op.update('challenges', sa.Column('value', sa.Integer(), nullable=False, server_default='1'), schema='new_stability')


def downgrade():
    # Remove value column from challenges table
    op.drop_column('challenges', 'value', schema='new_stability')
