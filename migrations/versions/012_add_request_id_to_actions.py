"""add request_id to actions

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-02-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a4b5c6d7e8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('actions', sa.Column('request_id', sa.String(255), nullable=True), schema='new_stability')
    op.create_unique_constraint('actions_unique_request_id', 'actions', ['request_id'], schema='new_stability')


def downgrade():
    op.drop_constraint('actions_unique_request_id', 'actions', schema='new_stability')
    op.drop_column('actions', 'request_id', schema='new_stability')
