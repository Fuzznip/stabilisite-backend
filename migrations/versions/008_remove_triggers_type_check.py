"""remove triggers type check constraint

Revision ID: d9e5f3b8c4a2
Revises: c8d4f2a7b3e1
Create Date: 2026-01-24

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd9e5f3b8c4a2'
down_revision = 'c8d4f2a7b3e1'
branch_labels = None
depends_on = None


def upgrade():
    # Remove the CHECK constraint on the type column
    op.drop_constraint('triggers_type_check', 'triggers', schema='new_stability', type_='check')


def downgrade():
    # Restore the CHECK constraint
    op.create_check_constraint(
        'triggers_type_check',
        'triggers',
        "type IN ('DROP', 'KC', 'SKILL', 'QUEST', 'ACHIEVEMENT', 'OTHER')",
        schema='new_stability'
    )
