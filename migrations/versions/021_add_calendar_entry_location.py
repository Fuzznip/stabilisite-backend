"""Add location and cover image to calendar_entries

Where a synced Discord event happens (a stage/voice channel, or free text such
as a text-channel mention or a link) and its cover photo.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-10-06

"""
from alembic import op
import sqlalchemy as sa

revision = 'c8d9e0f1a2b3'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('calendar_entries', sa.Column('location_channel_id', sa.String(32), nullable=True),
                  schema='new_stability')
    op.add_column('calendar_entries', sa.Column('location', sa.String(100), nullable=True),
                  schema='new_stability')
    op.add_column('calendar_entries', sa.Column('cover_image_url', sa.String(1024), nullable=True),
                  schema='new_stability')


def downgrade():
    op.drop_column('calendar_entries', 'cover_image_url', schema='new_stability')
    op.drop_column('calendar_entries', 'location', schema='new_stability')
    op.drop_column('calendar_entries', 'location_channel_id', schema='new_stability')
