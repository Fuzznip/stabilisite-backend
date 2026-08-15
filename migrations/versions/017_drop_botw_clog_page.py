"""Drop botw_bosses.clog_page

Boss drop lists are now supplied explicitly when the boss is created rather than
seeded from a collection log page, so the column that recorded which page they
came from no longer describes anything.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-08-15

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('botw_bosses', 'clog_page', schema='new_stability')


def downgrade():
    # Existing rows have no page to restore, so the column comes back filled
    # with the boss name — the value it defaulted to when seeding.
    op.add_column(
        'botw_bosses',
        sa.Column('clog_page', sa.String(255), nullable=True),
        schema='new_stability',
    )
    op.execute('UPDATE new_stability.botw_bosses SET clog_page = name WHERE clog_page IS NULL')
    op.alter_column('botw_bosses', 'clog_page', nullable=False, schema='new_stability')
