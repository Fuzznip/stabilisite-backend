"""create daily_riddles and daily_riddle_solutions tables

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-02-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'daily_riddles',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', UUID(as_uuid=True), sa.ForeignKey('new_stability.events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('riddle', sa.Text, nullable=False),
        sa.Column('item_name', sa.String(255), nullable=False),
        sa.Column('location', sa.String(255), nullable=False),
        sa.Column('image_link', sa.String(512), nullable=True),
        sa.Column('release_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_edited_timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        schema='new_stability'
    )

    op.create_table(
        'daily_riddle_solutions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('team_id', UUID(as_uuid=True), sa.ForeignKey('new_stability.teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('riddle_id', UUID(as_uuid=True), sa.ForeignKey('new_stability.daily_riddles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('solved_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('team_id', 'riddle_id', name='riddle_solutions_unique_team_riddle'),
        schema='new_stability'
    )


def downgrade():
    op.drop_table('daily_riddle_solutions', schema='new_stability')
    op.drop_table('daily_riddles', schema='new_stability')
