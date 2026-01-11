from app import db
from sqlalchemy.dialects.postgresql import UUID
from helper.helpers import Serializer
import uuid
import datetime

# =========================================
# NEW EVENT SYSTEM MODELS
# Schema: new_stability
# =========================================

class Event(db.Model, Serializer):
    __tablename__ = 'events'
    __table_args__ = {'schema': 'new_stability'}

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    start_date = db.Column(db.DateTime(timezone=True), nullable=False)
    end_date = db.Column(db.DateTime(timezone=True), nullable=False)
    thread_id = db.Column(db.String(255))  # Discord thread ID for notifications
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    teams = db.relationship('Team', back_populates='event', cascade='all, delete-orphan')
    tiles = db.relationship('Tile', back_populates='event', cascade='all, delete-orphan')

    def serialize(self):
        return Serializer.serialize(self)

    def is_active(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        return self.start_date <= now <= self.end_date


class Team(db.Model, Serializer):
    __tablename__ = 'teams'
    __table_args__ = (
        db.UniqueConstraint('event_id', 'name', name='teams_unique_name_per_event'),
        {'schema': 'new_stability'}
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.events.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.String(512))  # Team image/icon URL
    points = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    event = db.relationship('Event', back_populates='teams')
    members = db.relationship('TeamMember', back_populates='team', cascade='all, delete-orphan')
    tile_statuses = db.relationship('TileStatus', back_populates='team', cascade='all, delete-orphan')
    task_statuses = db.relationship('TaskStatus', back_populates='team', cascade='all, delete-orphan')
    challenge_statuses = db.relationship('ChallengeStatus', back_populates='team', cascade='all, delete-orphan')

    def serialize(self):
        return Serializer.serialize(self)


class TeamMember(db.Model, Serializer):
    __tablename__ = 'team_members'
    __table_args__ = (
        db.UniqueConstraint('team_id', 'user_id', name='team_members_unique_user_per_team'),
        {'schema': 'new_stability'}
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.teams.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    team = db.relationship('Team', back_populates='members')
    # user relationship points to public.users table (existing Users model)

    def serialize(self):
        return Serializer.serialize(self)


class Action(db.Model, Serializer):
    __tablename__ = 'actions'
    __table_args__ = {'schema': 'new_stability'}

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    type = db.Column(db.String(50), nullable=False, default='DROP')  # KC, DROP, QUEST, ACHIEVEMENT, DIARY, SKILL, etc.
    name = db.Column(db.String(255), nullable=False)
    source = db.Column(db.String(255))
    quantity = db.Column(db.Integer, nullable=False, default=1)
    value = db.Column(db.Integer)  # Item value or other numeric value associated with the action
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    challenge_proofs = db.relationship('ChallengeProof', back_populates='action', cascade='all, delete-orphan')

    def serialize(self):
        return Serializer.serialize(self)


class Trigger(db.Model, Serializer):
    __tablename__ = 'triggers'
    __table_args__ = (
        db.UniqueConstraint('name', 'source', name='triggers_unique_name_source'),
        {'schema': 'new_stability'}
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    source = db.Column(db.String(255))
    type = db.Column(db.String(50), nullable=False, default='DROP')
    img_path = db.Column(db.String(512))
    wiki_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    challenges = db.relationship('Challenge', back_populates='trigger')

    def serialize(self):
        return Serializer.serialize(self)


class Tile(db.Model, Serializer):
    __tablename__ = 'tiles'
    __table_args__ = (
        db.UniqueConstraint('event_id', 'index', name='tiles_unique_index_per_event'),
        {'schema': 'new_stability'}
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.events.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    img_src = db.Column(db.String(512))
    index = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    event = db.relationship('Event', back_populates='tiles')
    tasks = db.relationship('Task', back_populates='tile', cascade='all, delete-orphan')
    tile_statuses = db.relationship('TileStatus', back_populates='tile', cascade='all, delete-orphan')

    def serialize(self):
        return Serializer.serialize(self)


class Task(db.Model, Serializer):
    __tablename__ = 'tasks'
    __table_args__ = {'schema': 'new_stability'}

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tile_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.tiles.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    require_all = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    tile = db.relationship('Tile', back_populates='tasks')
    challenges = db.relationship('Challenge', back_populates='task', cascade='all, delete-orphan')
    task_statuses = db.relationship('TaskStatus', back_populates='task', cascade='all, delete-orphan')

    def serialize(self):
        return Serializer.serialize(self)


class Challenge(db.Model, Serializer):
    __tablename__ = 'challenges'
    __table_args__ = {'schema': 'new_stability'}

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.tasks.id', ondelete='CASCADE'), nullable=False)
    parent_challenge_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.challenges.id', ondelete='CASCADE'))
    trigger_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.triggers.id', ondelete='RESTRICT'), nullable=True)
    require_all = db.Column(db.Boolean, nullable=False, default=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    value = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    task = db.relationship('Task', back_populates='challenges')
    trigger = db.relationship('Trigger', back_populates='challenges')
    parent = db.relationship('Challenge', remote_side=[id], backref='children')
    challenge_statuses = db.relationship('ChallengeStatus', back_populates='challenge', cascade='all, delete-orphan')

    def serialize(self):
        return Serializer.serialize(self)


class TileStatus(db.Model, Serializer):
    __tablename__ = 'tile_statuses'
    __table_args__ = (
        db.UniqueConstraint('team_id', 'tile_id', name='tile_statuses_unique_team_tile'),
        {'schema': 'new_stability'}
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.teams.id', ondelete='CASCADE'), nullable=False)
    tile_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.tiles.id', ondelete='CASCADE'), nullable=False)
    tasks_completed = db.Column(db.Integer, nullable=False, default=0)  # 0=none, 1=bronze, 2=silver, 3=gold
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    team = db.relationship('Team', back_populates='tile_statuses')
    tile = db.relationship('Tile', back_populates='tile_statuses')

    def serialize(self):
        return Serializer.serialize(self)

    def get_medal_level(self):
        """Returns medal level: 'none', 'bronze', 'silver', 'gold'"""
        medal_map = {0: 'none', 1: 'bronze', 2: 'silver', 3: 'gold'}
        return medal_map.get(self.tasks_completed, 'none')


class TaskStatus(db.Model, Serializer):
    __tablename__ = 'task_statuses'
    __table_args__ = (
        db.UniqueConstraint('team_id', 'task_id', name='task_statuses_unique_team_task'),
        {'schema': 'new_stability'}
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.teams.id', ondelete='CASCADE'), nullable=False)
    task_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.tasks.id', ondelete='CASCADE'), nullable=False)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    team = db.relationship('Team', back_populates='task_statuses')
    task = db.relationship('Task', back_populates='task_statuses')

    def serialize(self):
        return Serializer.serialize(self)


class ChallengeStatus(db.Model, Serializer):
    __tablename__ = 'challenge_statuses'
    __table_args__ = (
        db.UniqueConstraint('team_id', 'challenge_id', name='challenge_statuses_unique_team_challenge'),
        {'schema': 'new_stability'}
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.teams.id', ondelete='CASCADE'), nullable=False)
    challenge_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.challenges.id', ondelete='CASCADE'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    team = db.relationship('Team', back_populates='challenge_statuses')
    challenge = db.relationship('Challenge', back_populates='challenge_statuses')
    proofs = db.relationship('ChallengeProof', back_populates='challenge_status', cascade='all, delete-orphan')

    def serialize(self):
        return Serializer.serialize(self)


class ChallengeProof(db.Model, Serializer):
    __tablename__ = 'challenge_proofs'
    __table_args__ = (
        db.UniqueConstraint('challenge_status_id', 'action_id', name='challenge_proofs_unique_status_action'),
        {'schema': 'new_stability'}
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    challenge_status_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.challenge_statuses.id', ondelete='CASCADE'), nullable=False)
    action_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.actions.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    challenge_status = db.relationship('ChallengeStatus', back_populates='proofs')
    action = db.relationship('Action', back_populates='challenge_proofs')

    def serialize(self):
        return Serializer.serialize(self)
