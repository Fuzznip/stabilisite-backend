"""Add boss of the week tables and make challenge progress player-aware

Boss of the week scores individuals, but challenge_statuses was keyed on a team.
This adds a nullable player_id, relaxes team_id, and swaps the single unique
constraint for two partial indexes so each owner kind keeps its own uniqueness.
Existing rows all have team_id, so they satisfy the new CHECK unchanged.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    # --- challenge_statuses: team-or-player ownership ---
    op.add_column(
        'challenge_statuses',
        sa.Column('player_id', postgresql.UUID(as_uuid=True), nullable=True),
        schema='new_stability',
    )
    op.create_foreign_key(
        'challenge_statuses_player_id_fkey',
        'challenge_statuses', 'users',
        ['player_id'], ['id'],
        source_schema='new_stability', referent_schema='public',
        ondelete='CASCADE',
    )
    op.alter_column('challenge_statuses', 'team_id', nullable=True, schema='new_stability')

    # One unique constraint can't express "unique per owner" when either owner
    # column may be NULL, so use a partial index per owner kind.
    op.drop_constraint(
        'challenge_statuses_unique_team_challenge',
        'challenge_statuses', schema='new_stability', type_='unique',
    )
    op.create_index(
        'uq_challenge_statuses_team_challenge',
        'challenge_statuses', ['team_id', 'challenge_id'],
        unique=True, schema='new_stability',
        postgresql_where=sa.text('team_id IS NOT NULL'),
    )
    op.create_index(
        'uq_challenge_statuses_player_challenge',
        'challenge_statuses', ['player_id', 'challenge_id'],
        unique=True, schema='new_stability',
        postgresql_where=sa.text('player_id IS NOT NULL'),
    )
    op.create_check_constraint(
        'challenge_statuses_one_owner',
        'challenge_statuses',
        '(team_id IS NULL) <> (player_id IS NULL)',
        schema='new_stability',
    )

    # --- botw_bosses ---
    op.create_table(
        'botw_bosses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('clog_page', sa.String(255), nullable=False),
        sa.Column('image_url', sa.String(512), nullable=True),
        sa.Column('display_order', sa.Integer, nullable=True),
        sa.Column('challenge_id', postgresql.UUID(as_uuid=True), nullable=True, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['event_id'], ['new_stability.events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['challenge_id'], ['new_stability.challenges.id'], ondelete='SET NULL'),
        schema='new_stability',
    )
    op.create_index('idx_botw_bosses_event_id', 'botw_bosses', ['event_id'], schema='new_stability')


def downgrade():
    op.drop_index('idx_botw_bosses_event_id', table_name='botw_bosses', schema='new_stability')
    op.drop_table('botw_bosses', schema='new_stability')

    # Player-owned rows can't survive a team-only constraint.
    op.execute('DELETE FROM new_stability.challenge_statuses WHERE player_id IS NOT NULL')

    op.drop_constraint('challenge_statuses_one_owner', 'challenge_statuses', schema='new_stability', type_='check')
    op.drop_index('uq_challenge_statuses_player_challenge', table_name='challenge_statuses', schema='new_stability')
    op.drop_index('uq_challenge_statuses_team_challenge', table_name='challenge_statuses', schema='new_stability')
    op.create_unique_constraint(
        'challenge_statuses_unique_team_challenge',
        'challenge_statuses', ['team_id', 'challenge_id'], schema='new_stability',
    )
    op.alter_column('challenge_statuses', 'team_id', nullable=False, schema='new_stability')
    op.drop_constraint('challenge_statuses_player_id_fkey', 'challenge_statuses', schema='new_stability', type_='foreignkey')
    op.drop_column('challenge_statuses', 'player_id', schema='new_stability')
