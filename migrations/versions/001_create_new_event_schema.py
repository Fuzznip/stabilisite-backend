"""Create new event system schema

Revision ID: 001_new_events
Revises:
Create Date: 2024-12-19 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_new_events'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create new_stability schema
    op.execute('CREATE SCHEMA IF NOT EXISTS new_stability')

    # Create events table
    op.create_table(
        'events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('thread_id', sa.String(255)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint('end_date > start_date', name='events_date_check'),
        schema='new_stability'
    )
    op.create_index('idx_events_dates', 'events', ['start_date', 'end_date'], schema='new_stability')

    # Create teams table
    op.create_table(
        'teams',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('image_url', sa.String(512)),
        sa.Column('points', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['event_id'], ['new_stability.events.id'], ondelete='CASCADE'),
        sa.CheckConstraint('points >= 0', name='teams_points_check'),
        sa.UniqueConstraint('event_id', 'name', name='teams_unique_name_per_event'),
        schema='new_stability'
    )
    op.create_index('idx_teams_event_id', 'teams', ['event_id'], schema='new_stability')
    op.create_index('idx_teams_points', 'teams', ['points'], schema='new_stability')

    # Create team_members table
    op.create_table(
        'team_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['team_id'], ['new_stability.teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['public.users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('team_id', 'user_id', name='team_members_unique_user_per_team'),
        schema='new_stability'
    )
    op.create_index('idx_team_members_team_id', 'team_members', ['team_id'], schema='new_stability')
    op.create_index('idx_team_members_user_id', 'team_members', ['user_id'], schema='new_stability')

    # Create actions table
    op.create_table(
        'actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('player_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('source', sa.String(255)),
        sa.Column('quantity', sa.Integer, nullable=False, server_default='1'),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['player_id'], ['public.users.id'], ondelete='CASCADE'),
        sa.CheckConstraint('quantity > 0', name='actions_quantity_check'),
        schema='new_stability'
    )
    op.create_index('idx_actions_player_id', 'actions', ['player_id'], schema='new_stability')
    op.create_index('idx_actions_date', 'actions', ['date'], schema='new_stability')
    op.create_index('idx_actions_name', 'actions', ['name'], schema='new_stability')
    op.create_index('idx_actions_name_source', 'actions', ['name', 'source'], schema='new_stability')

    # Create triggers table
    op.create_table(
        'triggers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('source', sa.String(255)),
        sa.Column('type', sa.String(50), nullable=False, server_default="'DROP'"),
        sa.Column('img_path', sa.String(512)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("type IN ('DROP', 'KC', 'SKILL', 'QUEST', 'ACHIEVEMENT', 'OTHER')", name='triggers_type_check'),
        sa.UniqueConstraint('name', 'source', name='triggers_unique_name_source'),
        schema='new_stability'
    )
    op.create_index('idx_triggers_name', 'triggers', ['name'], schema='new_stability')
    op.create_index('idx_triggers_name_source', 'triggers', ['name', 'source'], schema='new_stability')
    op.create_index('idx_triggers_type', 'triggers', ['type'], schema='new_stability')

    # Create tiles table
    op.create_table(
        'tiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('img_src', sa.String(512)),
        sa.Column('index', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['event_id'], ['new_stability.events.id'], ondelete='CASCADE'),
        sa.CheckConstraint('index >= 0 AND index <= 24', name='tiles_index_check'),
        sa.UniqueConstraint('event_id', 'index', name='tiles_unique_index_per_event'),
        schema='new_stability'
    )
    op.create_index('idx_tiles_event_id', 'tiles', ['event_id'], schema='new_stability')
    op.create_index('idx_tiles_index', 'tiles', ['event_id', 'index'], schema='new_stability')

    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tile_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('require_all', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['tile_id'], ['new_stability.tiles.id'], ondelete='CASCADE'),
        schema='new_stability'
    )
    op.create_index('idx_tasks_tile_id', 'tasks', ['tile_id'], schema='new_stability')

    # Create challenges table
    op.create_table(
        'challenges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parent_challenge_id', postgresql.UUID(as_uuid=True)),
        sa.Column('trigger_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('require_all', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('quantity', sa.Integer, nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['task_id'], ['new_stability.tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_challenge_id'], ['new_stability.challenges.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trigger_id'], ['new_stability.triggers.id'], ondelete='RESTRICT'),
        sa.CheckConstraint('quantity > 0', name='challenges_quantity_check'),
        schema='new_stability'
    )
    op.create_index('idx_challenges_task_id', 'challenges', ['task_id'], schema='new_stability')
    op.create_index('idx_challenges_parent_id', 'challenges', ['parent_challenge_id'], schema='new_stability')
    op.create_index('idx_challenges_trigger_id', 'challenges', ['trigger_id'], schema='new_stability')

    # Create tile_statuses table
    op.create_table(
        'tile_statuses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tile_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tasks_completed', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['team_id'], ['new_stability.teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tile_id'], ['new_stability.tiles.id'], ondelete='CASCADE'),
        sa.CheckConstraint('tasks_completed >= 0 AND tasks_completed <= 3', name='tile_statuses_tasks_check'),
        sa.UniqueConstraint('team_id', 'tile_id', name='tile_statuses_unique_team_tile'),
        schema='new_stability'
    )
    op.create_index('idx_tile_statuses_team_id', 'tile_statuses', ['team_id'], schema='new_stability')
    op.create_index('idx_tile_statuses_tile_id', 'tile_statuses', ['tile_id'], schema='new_stability')

    # Create task_statuses table
    op.create_table(
        'task_statuses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('completed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['team_id'], ['new_stability.teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['new_stability.tasks.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('team_id', 'task_id', name='task_statuses_unique_team_task'),
        schema='new_stability'
    )
    op.create_index('idx_task_statuses_team_id', 'task_statuses', ['team_id'], schema='new_stability')
    op.create_index('idx_task_statuses_task_id', 'task_statuses', ['task_id'], schema='new_stability')
    op.create_index('idx_task_statuses_completed', 'task_statuses', ['team_id', 'completed'], schema='new_stability')

    # Create challenge_statuses table
    op.create_table(
        'challenge_statuses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('challenge_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('quantity', sa.Integer, nullable=False, server_default='0'),
        sa.Column('completed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['team_id'], ['new_stability.teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['challenge_id'], ['new_stability.challenges.id'], ondelete='CASCADE'),
        sa.CheckConstraint('quantity >= 0', name='challenge_statuses_quantity_check'),
        sa.UniqueConstraint('team_id', 'challenge_id', name='challenge_statuses_unique_team_challenge'),
        schema='new_stability'
    )
    op.create_index('idx_challenge_statuses_team_id', 'challenge_statuses', ['team_id'], schema='new_stability')
    op.create_index('idx_challenge_statuses_challenge_id', 'challenge_statuses', ['challenge_id'], schema='new_stability')
    op.create_index('idx_challenge_statuses_completed', 'challenge_statuses', ['team_id', 'completed'], schema='new_stability')

    # Create challenge_proofs table
    op.create_table(
        'challenge_proofs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('challenge_status_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['challenge_status_id'], ['new_stability.challenge_statuses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['action_id'], ['new_stability.actions.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('challenge_status_id', 'action_id', name='challenge_proofs_unique_status_action'),
        schema='new_stability'
    )
    op.create_index('idx_challenge_proofs_status_id', 'challenge_proofs', ['challenge_status_id'], schema='new_stability')
    op.create_index('idx_challenge_proofs_action_id', 'challenge_proofs', ['action_id'], schema='new_stability')

    # Create updated_at trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION new_stability.update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # Apply triggers to all tables with updated_at
    for table in ['events', 'teams', 'team_members', 'triggers', 'tiles', 'tasks', 'challenges',
                  'tile_statuses', 'task_statuses', 'challenge_statuses']:
        op.execute(f"""
            CREATE TRIGGER update_{table}_updated_at
            BEFORE UPDATE ON new_stability.{table}
            FOR EACH ROW EXECUTE FUNCTION new_stability.update_updated_at_column();
        """)


def downgrade():
    # Drop all tables in reverse order
    op.drop_table('challenge_proofs', schema='new_stability')
    op.drop_table('challenge_statuses', schema='new_stability')
    op.drop_table('task_statuses', schema='new_stability')
    op.drop_table('tile_statuses', schema='new_stability')
    op.drop_table('challenges', schema='new_stability')
    op.drop_table('tasks', schema='new_stability')
    op.drop_table('tiles', schema='new_stability')
    op.drop_table('triggers', schema='new_stability')
    op.drop_table('actions', schema='new_stability')
    op.drop_table('team_members', schema='new_stability')
    op.drop_table('teams', schema='new_stability')
    op.drop_table('events', schema='new_stability')

    # Drop function
    op.execute('DROP FUNCTION IF EXISTS new_stability.update_updated_at_column()')

    # Drop schema
    op.execute('DROP SCHEMA IF EXISTS new_stability CASCADE')
