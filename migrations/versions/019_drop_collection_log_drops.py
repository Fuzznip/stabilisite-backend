"""Drop collection_log_drops

The persistent clan collection log is replaced by the collection log race event,
which stores progress as ordinary team-owned challenge statuses. The catalog
table (collection_log_items) stays: it is the generator input for those events.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'a6b7c8d9e0f1'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('collection_log_drops')


def downgrade():
    # The table comes back empty; the drop history is not recoverable.
    op.create_table(
        'collection_log_drops',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('discord_id', sa.String(), sa.ForeignKey('users.discord_id', ondelete='CASCADE'), nullable=True),
        sa.Column('rsn', sa.String(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False, index=True),
        sa.Column('item_name', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('value', sa.Integer(), server_default='0'),
        sa.Column('screenshot', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
