"""Make challenge trigger_id nullable for parent challenges

Revision ID: 003_trigger_nullable
Revises: 002_action_type
Create Date: 2026-01-03 22:00:00.000000

This allows parent challenges to exist without a trigger, enabling
nested challenge structures like:
  (Quest OR Diary) AND (Boss kills)
  ├─ Parent 1 (OR): trigger_id=NULL, has children
  │  ├─ Child: Quest trigger
  │  └─ Child: Diary trigger
  └─ Parent 2 (AND): Boss trigger

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_trigger_nullable'
down_revision = '002_action_type'
branch_labels = None
depends_on = None


def upgrade():
    # Make trigger_id nullable in challenges table
    op.alter_column(
        'challenges',
        'trigger_id',
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=True,
        schema='new_stability'
    )


def downgrade():
    # Revert trigger_id to NOT NULL
    # Note: This will fail if there are any parent challenges with NULL trigger_id
    op.alter_column(
        'challenges',
        'trigger_id',
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=False,
        schema='new_stability'
    )
