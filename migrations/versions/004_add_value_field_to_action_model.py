"""Add value field to Action model

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-01-04 21:04:34.784698

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    # Add value column to actions table
    op.add_column('actions', sa.Column('value', sa.Integer(), nullable=True), schema='new_stability')


def downgrade():
    # Remove value column from actions table
    op.drop_column('actions', 'value', schema='new_stability')
