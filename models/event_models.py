from app import db
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from helper.helpers import Serializer
import uuid
import datetime

class Trigger(db.Model, Serializer):
    __tablename__ = 'ev2_triggers'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String, nullable=False)
    type = db.Column(db.String, nullable=False) # 'Item', 'Pet', 'Kill', 'Chat'

class Source(db.Model, Serializer):
    __tablename__ = 'ev2_sources'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String, nullable=False)

class Quest(db.Model, Serializer):
    __tablename__ = 'ev2_quests'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=True)

    requirement_set = db.relationship('RequirementSet', backref='quest', lazy=True, uselist=False)

class RequirementSet(db.Model, Serializer):
    __tablename__ = 'ev2_requirement_sets'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quest_id = db.Column(UUID(as_uuid=True), db.ForeignKey('ev2_quests.id'), nullable=False)
    logical_operator = db.Column(db.String, nullable=False) # 'AND', 'OR'
    required_quantity = db.Column(db.Integer, nullable=False, default=1)

    quest = db.relationship('Quest', backref=db.backref('requirement_sets', lazy=True))
    child_groups = db.relationship('RequirementGroup', backref=db.backref('parent_set', remote_side=[id]), lazy=True)

class RequirementGroup(db.Model, Serializer):
    __tablename__ = 'ev2_requirement_group'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_set_id = db.Column(UUID(as_uuid=True), db.ForeignKey('ev2_requirement_sets.id'), nullable=False)
    parent_group_id = db.Column(UUID(as_uuid=True), db.ForeignKey('ev2_requirement_group.id'), nullable=True)
    logical_operator = db.Column(db.String, nullable=False) # 'AND', 'OR'
    required_quantity = db.Column(db.Integer, nullable=False, default=1)

    parent_set = db.relationship('RequirementSet', backref=db.backref('requirement_groups', lazy=True))
    parent_group = db.relationship('RequirementGroup', backref=db.backref('child_groups', remote_side=[id]), lazy=True)
    child_groups = db.relationship('RequirementGroup', backref=db.backref('parent_group', remote_side=[id]), lazy=True)
    requirements = db.relationship('Requirement', backref='requirement_group', lazy=True)

class Requirement(db.Model, Serializer):
    __tablename__ = 'ev2_requirements'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = db.Column(UUID(as_uuid=True), db.ForeignKey('ev2_requirement_group.id'), nullable=False)
    trigger_id = db.Column(UUID(as_uuid=True), db.ForeignKey('ev2_triggers.id'), nullable=False)
    metric = db.Column(db.String, nullable=False, default='DROP') # 'DROP', 'KC', 'CHAT'
    weight = db.Column(db.Float, nullable=False, default=1.0)

    group = db.relationship('RequirementGroup', backref=db.backref('requirements', lazy=True))
    trigger = db.relationship('Trigger', backref=db.backref('requirements', lazy=True))
    sources = db.relationship('Source', secondary='ev2_requirement_sources', backref='requirements')

class RequirementSource(db.Model):
    __tablename__ = 'ev2_requirement_sources'
    requirement_id = db.Column(UUID(as_uuid=True), db.ForeignKey('ev2_requirements.id'), primary_key=True)
    source_id = db.Column(UUID(as_uuid=True), db.ForeignKey('ev2_sources.id'), primary_key=True)

class EventTeam(db.Model, Serializer):
    __tablename__ = 'ev2_event_teams'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = db.Column(UUID(as_uuid=True), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.datetime.now(datetime.timezone.utc), onupdate=datetime.datetime.now(datetime.timezone.utc))

    data = db.Column(JSONB, nullable=False, default={})

