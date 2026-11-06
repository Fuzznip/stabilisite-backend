"""Backend-owned trial board tables; starts paused.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
"""
from alembic import op
import sqlalchemy as sa

revision = 'd9e0f1a2b3c4'
down_revision = 'c8d9e0f1a2b3'
branch_labels = None
depends_on = None


def upgrade():
    # New tables only; no existing clan records or admission policy changes.
    op.create_table('trial_board_audit',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('actor', sa.BigInteger(), nullable=True),
    sa.Column('action', sa.String(length=60), nullable=False),
    sa.Column('trial', sa.Integer(), nullable=True),
    sa.Column('created', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='new_stability'
    )
    op.create_table('trial_board_state',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('paused', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('worker', sa.String(length=64), nullable=True),
    sa.Column('expires', sa.BigInteger(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='new_stability'
    )
    op.create_table('trial_board_trials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('applicant', sa.BigInteger(), nullable=False),
    sa.Column('channel', sa.BigInteger(), nullable=False),
    sa.Column('board', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='availability', nullable=False),
    sa.Column('windows', sa.Text(), server_default='[]', nullable=False),
    sa.Column('zone', sa.String(length=80), server_default='UTC', nullable=False),
    sa.Column('duration', sa.Integer(), nullable=False),
    sa.Column('owner', sa.BigInteger(), nullable=True),
    sa.Column('start', sa.BigInteger(), nullable=True),
    sa.Column('end', sa.BigInteger(), nullable=True),
    sa.Column('created', sa.BigInteger(), nullable=False),
    sa.Column('deadline', sa.BigInteger(), nullable=False),
    sa.Column('revision', sa.Integer(), server_default='1', nullable=False),
    sa.Column('card', sa.BigInteger(), nullable=True),
    sa.Column('outcome', sa.String(length=16), nullable=True),
    sa.Column('proposal_expires', sa.BigInteger(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='new_stability'
    )
    op.create_index('uq_trial_board_active_applicant', 'trial_board_trials', ['applicant'], unique=True, schema='new_stability', postgresql_where=sa.text("(status NOT IN ('closed', 'cancelled'))"), sqlite_where=sa.text("(status NOT IN ('closed', 'cancelled'))"))
    op.create_table('trial_board_volunteers',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('board', sa.String(length=16), nullable=False),
    sa.Column('approved', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('capacity', sa.Integer(), server_default='2', nullable=False),
    sa.Column('windows', sa.Text(), server_default='[]', nullable=False),
    sa.Column('zone', sa.String(length=80), server_default='UTC', nullable=False),
    sa.Column('offered', sa.BigInteger(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('user_id'),
    schema='new_stability'
    )
    op.create_table('trial_board_feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trial', sa.Integer(), nullable=False),
    sa.Column('author', sa.BigInteger(), nullable=False),
    sa.Column('recommendation', sa.String(length=16), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['trial'], ['new_stability.trial_board_trials.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trial', 'author', name='uq_trial_board_feedback_author'),
    schema='new_stability'
    )
    op.create_table('trial_board_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dedupe', sa.String(length=180), nullable=False),
    sa.Column('trial', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('data', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
    sa.Column('message', sa.BigInteger(), nullable=True),
    sa.Column('channel', sa.BigInteger(), nullable=True),
    sa.Column('created', sa.BigInteger(), nullable=False),
    sa.Column('error', sa.String(length=120), nullable=True),
    sa.Column('claim_token', sa.String(length=64), nullable=True),
    sa.Column('claimed_at', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['trial'], ['new_stability.trial_board_trials.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dedupe'),
    schema='new_stability'
    )
    op.create_index('ix_trial_board_pending_jobs', 'trial_board_jobs', ['status', 'id'], unique=False, schema='new_stability')
    op.create_table('trial_board_requests',
    sa.Column('request_key', sa.String(length=100), nullable=False),
    sa.Column('applicant', sa.BigInteger(), nullable=False),
    sa.Column('channel', sa.BigInteger(), nullable=False),
    sa.Column('board', sa.String(length=16), nullable=False),
    sa.Column('duration', sa.Integer(), nullable=False),
    sa.Column('trial', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['trial'], ['new_stability.trial_board_trials.id'], ),
    sa.PrimaryKeyConstraint('request_key'),
    schema='new_stability'
    )
    op.bulk_insert(sa.Table('trial_board_state', sa.MetaData(), sa.Column('id', sa.Integer),
        sa.Column('paused', sa.Boolean), schema='new_stability'), [{'id': 1, 'paused': True}])


def downgrade():
    op.drop_table('trial_board_requests', schema='new_stability')
    op.drop_table('trial_board_jobs', schema='new_stability')
    op.drop_table('trial_board_feedback', schema='new_stability')
    op.drop_table('trial_board_volunteers', schema='new_stability')
    op.drop_table('trial_board_trials', schema='new_stability')
    op.drop_table('trial_board_state', schema='new_stability')
    op.drop_table('trial_board_audit', schema='new_stability')
