"""Add calendar_entries

Planned clan events shown on the home-page calendar, optionally mirrored to a
Discord scheduled event.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b7c8d9e0f1a2'
down_revision = 'a6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'calendar_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('all_day', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('sync_discord', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('discord_event_id', sa.String(32), nullable=True),
        sa.Column('event_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('new_stability.events.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        schema='new_stability',
    )
    op.create_index('ix_new_stability_calendar_entries_start_date', 'calendar_entries',
                    ['start_date'], schema='new_stability')


def downgrade():
    op.drop_index('ix_new_stability_calendar_entries_start_date', table_name='calendar_entries',
                  schema='new_stability')
    op.drop_table('calendar_entries', schema='new_stability')
