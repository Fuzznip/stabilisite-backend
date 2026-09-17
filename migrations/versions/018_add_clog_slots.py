"""Add clog_slots for the collection log race event

One row per collection log slot in a 'clog' event, anchoring the Challenge that
carries its point value and the teams' progress.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'f5a6b7c8d9e0'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'clog_slots',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', UUID(as_uuid=True), sa.ForeignKey('new_stability.events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('page', sa.String(255), nullable=False),
        sa.Column('page_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sequence', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('image_url', sa.String(512), nullable=True),
        sa.Column('challenge_id', UUID(as_uuid=True), sa.ForeignKey('new_stability.challenges.id', ondelete='SET NULL'), nullable=True, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('event_id', 'item_id', name='clog_slots_unique_item_per_event'),
        schema='new_stability',
    )
    op.create_index('idx_clog_slots_event', 'clog_slots', ['event_id'], schema='new_stability')


def downgrade():
    op.drop_index('idx_clog_slots_event', table_name='clog_slots', schema='new_stability')
    op.drop_table('clog_slots', schema='new_stability')
