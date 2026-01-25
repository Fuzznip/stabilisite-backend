"""Add action type column and optimize proof creation

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-03 21:00:00.000000

Changes:
1. Add 'type' column to actions table for semantic action classification
2. Add index on type column for filtering performance
3. Note: Proof optimization is handled in application logic (action_processor.py)

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Add type column to actions table with default 'DROP'
    op.add_column(
        'actions',
        sa.Column('type', sa.String(50), nullable=False, server_default='DROP'),
        schema='new_stability'
    )

    # Add index on type column for filtering
    op.create_index(
        'idx_actions_type',
        'actions',
        ['type'],
        schema='new_stability'
    )


def downgrade():
    # Drop index
    op.drop_index('idx_actions_type', table_name='actions', schema='new_stability')

    # Drop type column
    op.drop_column('actions', 'type', schema='new_stability')
