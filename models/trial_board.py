"""Backend-owned trial tables. Discord snowflakes are 64-bit integers."""
import sqlalchemy as sa

metadata = sa.MetaData(schema='new_stability')

state = sa.Table('trial_board_state', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('paused', sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column('worker', sa.String(64)), sa.Column('expires', sa.BigInteger))
volunteers = sa.Table('trial_board_volunteers', metadata,
    sa.Column('user_id', sa.BigInteger, primary_key=True),
    sa.Column('board', sa.String(16), nullable=False),
    sa.Column('approved', sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column('active', sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column('capacity', sa.Integer, nullable=False, server_default='2'),
    sa.Column('windows', sa.Text, nullable=False, server_default='[]'),
    sa.Column('zone', sa.String(80), nullable=False, server_default='UTC'),
    sa.Column('offered', sa.BigInteger, nullable=False, server_default='0'))
trials = sa.Table('trial_board_trials', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('applicant', sa.BigInteger, nullable=False),
    sa.Column('channel', sa.BigInteger, nullable=False),
    sa.Column('board', sa.String(16), nullable=False),
    sa.Column('status', sa.String(20), nullable=False, server_default='availability'),
    sa.Column('windows', sa.Text, nullable=False, server_default='[]'),
    sa.Column('zone', sa.String(80), nullable=False, server_default='UTC'),
    sa.Column('duration', sa.Integer, nullable=False),
    sa.Column('owner', sa.BigInteger), sa.Column('start', sa.BigInteger),
    sa.Column('end', sa.BigInteger), sa.Column('created', sa.BigInteger, nullable=False),
    sa.Column('deadline', sa.BigInteger, nullable=False),
    sa.Column('revision', sa.Integer, nullable=False, server_default='1'),
    sa.Column('card', sa.BigInteger), sa.Column('outcome', sa.String(16)),
    sa.Column('proposal_expires', sa.BigInteger))
sa.Index('uq_trial_board_active_applicant', trials.c.applicant, unique=True,
         postgresql_where=trials.c.status.not_in(['closed', 'cancelled']),
         sqlite_where=trials.c.status.not_in(['closed', 'cancelled']))
feedback = sa.Table('trial_board_feedback', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('trial', sa.Integer, sa.ForeignKey(trials.c.id), nullable=False),
    sa.Column('author', sa.BigInteger, nullable=False),
    sa.Column('recommendation', sa.String(16), nullable=False),
    sa.Column('notes', sa.Text, nullable=False),
    sa.Column('created', sa.BigInteger, nullable=False),
    sa.UniqueConstraint('trial', 'author', name='uq_trial_board_feedback_author'))
jobs = sa.Table('trial_board_jobs', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('dedupe', sa.String(180), unique=True, nullable=False),
    sa.Column('trial', sa.Integer, sa.ForeignKey(trials.c.id), nullable=False),
    sa.Column('revision', sa.Integer, nullable=False),
    sa.Column('kind', sa.String(20), nullable=False),
    sa.Column('data', sa.Text, nullable=False),
    sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
    sa.Column('message', sa.BigInteger), sa.Column('channel', sa.BigInteger),
    sa.Column('created', sa.BigInteger, nullable=False), sa.Column('error', sa.String(120)),
    sa.Column('claim_token', sa.String(64)), sa.Column('claimed_at', sa.BigInteger))
sa.Index('ix_trial_board_pending_jobs', jobs.c.status, jobs.c.id)
audit = sa.Table('trial_board_audit', metadata,
    sa.Column('id', sa.Integer, primary_key=True), sa.Column('actor', sa.BigInteger),
    sa.Column('action', sa.String(60), nullable=False), sa.Column('trial', sa.Integer),
    sa.Column('created', sa.BigInteger, nullable=False))
requests = sa.Table('trial_board_requests', metadata,
    sa.Column('request_key', sa.String(100), primary_key=True),
    sa.Column('applicant', sa.BigInteger, nullable=False),
    sa.Column('channel', sa.BigInteger, nullable=False),
    sa.Column('board', sa.String(16), nullable=False),
    sa.Column('duration', sa.Integer, nullable=False),
    sa.Column('trial', sa.Integer, sa.ForeignKey(trials.c.id), nullable=False))
