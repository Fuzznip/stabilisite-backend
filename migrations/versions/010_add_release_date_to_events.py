"""add release_date to events

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('release_date', sa.DateTime(timezone=True), nullable=True), schema='new_stability')


def downgrade():
    op.drop_column('events', 'release_date', schema='new_stability')
