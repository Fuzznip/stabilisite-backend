"""Add value field to Action model

Revision ID: ae00dc5bd504
Revises: 003_trigger_nullable
Create Date: 2026-01-04 21:04:34.784698

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ae00dc5bd504'
down_revision = '003_trigger_nullable'
branch_labels = None
depends_on = None


def upgrade():
    # Add value column to actions table
    op.add_column('actions', sa.Column('value', sa.Integer(), nullable=True), schema='new_stability')


def downgrade():
    # Remove value column from actions table
    op.drop_column('actions', 'value', schema='new_stability')
