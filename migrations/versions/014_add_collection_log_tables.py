"""Add collection log catalog and drops tables

These were previously only created ad-hoc by scripts/seed_collection_log.py,
which meant any database that had not been seeded by hand was missing them and
every /collection-log endpoint returned UndefinedTable. Creating them here makes
`flask db upgrade` sufficient.

Both tables live in the default (public) schema, matching models.py — unlike the
conquest/bingo tables, which use the new_stability schema.

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f4
Create Date: 2026-07-30

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def upgrade():
    # An item can appear on multiple pages (shared clue rewards, pets that also
    # show under "All Pets"), so the natural key is (item_id, page), not item_id.
    op.create_table(
        'collection_log_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('item_id', sa.Integer, nullable=False),
        sa.Column('name', sa.String, nullable=False),
        sa.Column('category', sa.String, nullable=False),
        sa.Column('page', sa.String, nullable=False),
        sa.Column('page_order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('sequence', sa.Integer, nullable=False, server_default='0'),
        sa.Column('image_url', sa.String, nullable=True),
    )
    op.create_unique_constraint(
        'uq_collection_log_item_page', 'collection_log_items', ['item_id', 'page']
    )
    op.create_index(
        'ix_collection_log_items_item_id', 'collection_log_items', ['item_id']
    )

    # One row per received drop (duplicates kept) so we can show per-member
    # counts and first/last dates. discord_id is nullable because a Dink
    # submission's RSN may not match a known member.
    op.create_table(
        'collection_log_drops',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('discord_id', sa.String, sa.ForeignKey('users.discord_id', ondelete='CASCADE'), nullable=True),
        sa.Column('rsn', sa.String, nullable=False),
        sa.Column('item_id', sa.Integer, nullable=False),
        sa.Column('item_name', sa.String, nullable=True),
        sa.Column('source', sa.String, nullable=True),
        sa.Column('quantity', sa.Integer, nullable=False, server_default='1'),
        sa.Column('value', sa.Integer, server_default='0'),
        sa.Column('screenshot', sa.String, nullable=True),
        sa.Column('timestamp', sa.DateTime, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index(
        'ix_collection_log_drops_item_id', 'collection_log_drops', ['item_id']
    )


def downgrade():
    op.drop_index('ix_collection_log_drops_item_id', table_name='collection_log_drops')
    op.drop_table('collection_log_drops')
    op.drop_index('ix_collection_log_items_item_id', table_name='collection_log_items')
    op.drop_constraint('uq_collection_log_item_page', 'collection_log_items', type_='unique')
    op.drop_table('collection_log_items')
