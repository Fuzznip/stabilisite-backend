"""Add challenges.min_quantity_per_action

The column was added to the model and is read by the conquest and boss of the
week handlers, but no migration ever created it — it was added to the deployed
database by hand, so any database built from migrations alone was missing it and
every challenge insert failed with UndefinedColumn.

Written as ADD COLUMN IF NOT EXISTS so it is a no-op where the column already
exists.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-07

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE new_stability.challenges ADD COLUMN IF NOT EXISTS min_quantity_per_action INTEGER')


def downgrade():
    op.execute('ALTER TABLE new_stability.challenges DROP COLUMN IF EXISTS min_quantity_per_action')
