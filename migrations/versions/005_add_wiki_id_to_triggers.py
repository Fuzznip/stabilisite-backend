"""add wiki_id to triggers

Revision ID: b72f3e9a8c41
Revises: ae00dc5bd504
Create Date: 2026-01-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b72f3e9a8c41'
down_revision = 'ae00dc5bd504'
branch_labels = None
depends_on = None


def upgrade():
    # Add wiki_id column to triggers table
    op.add_column('triggers', sa.Column('wiki_id', sa.Integer(), nullable=True), schema='new_stability')


def downgrade():
    # Remove wiki_id column from triggers table
    op.drop_column('triggers', 'wiki_id', schema='new_stability')
