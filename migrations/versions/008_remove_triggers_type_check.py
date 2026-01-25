"""remove triggers type check constraint

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-01-24

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
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
