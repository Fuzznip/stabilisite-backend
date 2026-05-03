"""Add conquest event tables and schema changes

Revision ID: a9b0c1d2e3f4
Revises: f3a4b5c6d7e8
Create Date: 2026-05-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a9b0c1d2e3f4'
down_revision = 'f3a4b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade():
    # Add type to events
    op.add_column('events', sa.Column('type', sa.String(50), nullable=True), schema='new_stability')

    # Make challenge task_id nullable (conquest challenges are not tied to a tile/task)
    op.alter_column('challenges', 'task_id', nullable=True, schema='new_stability')

    # Create regions table
    op.create_table(
        'regions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('controlling_team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('green_logged_teams', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default='{}'),
        sa.Column('image_url', sa.String(512), nullable=True),
        sa.Column('offset_x', sa.Integer, nullable=True),
        sa.Column('offset_y', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['event_id'], ['new_stability.events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['controlling_team_id'], ['new_stability.teams.id'], ondelete='SET NULL'),
        schema='new_stability'
    )
    op.create_index('idx_regions_event_id', 'regions', ['event_id'], schema='new_stability')

    # Create territories table (challenge_id is a direct FK — one territory owns one challenge)
    op.create_table(
        'territories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('region_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('tier', sa.String(50), nullable=True),
        sa.Column('challenge_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('controlling_team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('display_order', sa.Integer, nullable=True),
        sa.Column('offset_x', sa.Integer, nullable=True),
        sa.Column('offset_y', sa.Integer, nullable=True),
        sa.Column('polygon_points', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['region_id'], ['new_stability.regions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['challenge_id'], ['new_stability.challenges.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['controlling_team_id'], ['new_stability.teams.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('challenge_id', name='territories_unique_challenge'),
        schema='new_stability'
    )
    op.create_index('idx_territories_region_id', 'territories', ['region_id'], schema='new_stability')

    # Create event_logs table
    op.create_table(
        'event_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('meta', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['event_id'], ['new_stability.events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['new_stability.teams.id'], ondelete='CASCADE'),
        schema='new_stability'
    )
    op.create_index('idx_event_logs_event_created', 'event_logs', ['event_id', 'created_at'], schema='new_stability')
    op.create_index('idx_event_logs_event_type', 'event_logs', ['event_id', 'type'], schema='new_stability')
    op.create_index('idx_event_logs_entity', 'event_logs', ['entity_id', 'type'], schema='new_stability')


def downgrade():
    op.drop_table('event_logs', schema='new_stability')
    op.drop_table('territories', schema='new_stability')
    op.drop_table('regions', schema='new_stability')
    op.alter_column('challenges', 'task_id', nullable=False, schema='new_stability')
    op.drop_column('events', 'type', schema='new_stability')
