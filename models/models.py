from app import db
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func
from helper.helpers import Serializer
import uuid
import datetime

class Users(db.Model, Serializer):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discord_id = db.Column(db.String, unique=True, nullable=False)
    discord_avatar_url= db.Column(db.String, default="https://i.imgur.com/4LdSYto.jpeg")
    runescape_name = db.Column(db.String, nullable=False)
    previous_names = db.Column(ARRAY(db.String), default=[])
    alt_names = db.Column(ARRAY(db.String), default=[])
    is_member = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    rank = db.Column(db.String, default='Guest')
    rank_points = db.Column(db.Numeric, default=0)
    progression_data = db.Column(JSONB, default={})
    achievements = db.Column(ARRAY(db.String), default=[])
    join_date = db.Column(db.DateTime)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    is_active = db.Column(db.Boolean, default=True)
    diary_points = db.Column(db.Numeric, default=0)
    event_points = db.Column(db.Numeric, default=0)
    time_points = db.Column(db.Numeric, default=0)
    split_points = db.Column(db.Numeric, default=0)
    raid_tier_points = db.Column(db.Numeric, default=0)
    settings = db.Column(JSONB, default={})

    def serialize(self):
        return Serializer.serialize(self)

class Announcements(db.Model, Serializer):
    __tablename__ = 'announcements'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id = db.Column(db.String, db.ForeignKey('users.discord_id', ondelete="CASCADE"))  # Cascade delete
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    is_pinned = db.Column(db.Boolean)

    def serialize(self):
        return Serializer.serialize(self)

class Splits(db.Model, Serializer):
    __tablename__ = 'splits'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String, db.ForeignKey('users.discord_id', ondelete="CASCADE"))  # Cascade delete
    item_name = db.Column(db.String, nullable=False)
    item_price = db.Column(db.Numeric, nullable=False)
    item_id = db.Column(db.String, nullable=False)
    split_contribution = db.Column(db.Numeric, nullable=False)
    group_size = db.Column(db.Integer, nullable=False)
    screenshot_link = db.Column(db.String)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)

class ClanApplications(db.Model, Serializer):
    __tablename__ = 'applications'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String)
    runescape_name = db.Column(db.String, nullable=False)
    referral = db.Column(db.String)
    reason = db.Column(db.Text)
    goals = db.Column(db.Text)
    status = db.Column(db.String, default='Pending')
    verdict_reason = db.Column(db.Text)
    verdict_timestamp = db.Column(db.DateTime, default=datetime.datetime.now(datetime.timezone.utc))
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)

class ClanRanks(db.Model, Serializer):
    __tablename__ = 'clan_ranks'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rank_name = db.Column(db.String, nullable=False)
    rank_minimum_points = db.Column(db.Integer, nullable=False)
    rank_minimum_days = db.Column(db.Integer, nullable=False)
    rank_order = db.Column(db.Integer, nullable=False)
    rank_icon = db.Column(db.String)
    rank_color = db.Column(db.String)
    rank_description = db.Column(db.Text)
    rank_requirements = db.Column(ARRAY(db.String))

    def serialize(self):
        return Serializer.serialize(self)

class RaidTiers(db.Model, Serializer):
    __tablename__ = 'raid_tiers'
    __table_args__ = (db.UniqueConstraint('tier_name', 'tier_order'),)
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier_name = db.Column(db.String, nullable=False)
    tier_order = db.Column(db.Integer, nullable=False)
    tier_icon = db.Column(db.String)
    tier_color = db.Column(db.String)
    tier_description = db.Column(db.Text)
    tier_requirements = db.Column(db.Text)
    tier_points = db.Column(db.Integer, nullable=False)
    tier_role_name = db.Column(db.String)

    def serialize(self):
        return Serializer.serialize(self)

class Achievements(db.Model, Serializer):
    __tablename__ = 'achievements'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String, db.ForeignKey('users.discord_id', ondelete="CASCADE"))  # Cascade delete
    achievement_name = db.Column(db.String, nullable=False)
    achievement_points = db.Column(db.Integer, nullable=False)
    achievement_color = db.Column(db.String)
    achievement_image = db.Column(db.String)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)

class RankApplications(db.Model, Serializer):
    __tablename__ = 'rank_applications'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String)
    runescape_name = db.Column(db.String, nullable=False)
    desired_rank = db.Column(db.String, nullable=False)
    proof = db.Column(ARRAY(db.String))
    status = db.Column(db.String, default='Pending')
    verdict_reason = db.Column(db.Text)
    verdict_timestamp = db.Column(db.DateTime)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)

class TierApplications(db.Model, Serializer):
    __tablename__ = 'tier_applications'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String)
    runescape_name = db.Column(db.String, nullable=False)
    desired_tier = db.Column(db.String, nullable=False)
    proof = db.Column(db.String)
    status = db.Column(db.String, default='Pending')
    verdict_reason = db.Column(db.Text)
    verdict_timestamp = db.Column(db.DateTime)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)

class BossDictionary(db.Model, Serializer):
    __tablename__ = 'boss_dictionary'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String, unique=True, nullable=False)
    shorthand = db.Column(db.String, nullable=False)
    icon = db.Column(db.String)

    def serialize(self):
        return Serializer.serialize(self)

class TimeSplitApplications(db.Model, Serializer):
    __tablename__ = 'time_split_applications'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String, db.ForeignKey('users.discord_id', ondelete="CASCADE"))  # Cascade delete
    boss_name = db.Column(db.String, nullable=False)
    split = db.Column(db.String, nullable=False)
    players = db.Column(ARRAY(db.String))
    scale = db.Column(db.String)
    proof = db.Column(db.String)
    verification_status = db.Column(db.String, default='Pending')
    verification_reason = db.Column(db.Text)
    verification_timestamp = db.Column(db.DateTime)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)
    
class TimeSplitsLog(db.Model, Serializer):
    __tablename__ = 'time_splits_log'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submitter_id = db.Column(db.String, db.ForeignKey('users.discord_id', ondelete="CASCADE"))  # Cascade delete
    boss = db.Column(db.String, db.ForeignKey('boss_dictionary.name', ondelete="CASCADE"))  # Cascade delete
    split = db.Column(db.String, nullable=False)
    players = db.Column(ARRAY(db.String))
    scale = db.Column(db.String)
    proof = db.Column(db.String)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)

class DiaryTasks(db.Model, Serializer):
    __tablename__ = 'diary_content'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diary_name = db.Column(db.String, nullable=False)
    diary_shorthand = db.Column(db.String)
    boss_name = db.Column(db.String)
    scale = db.Column(db.String)
    diary_description = db.Column(db.Text)
    diary_time = db.Column(db.String)
    diary_points = db.Column(db.Integer, nullable=False)

    def serialize(self):
        return Serializer.serialize(self)

class DiaryApplications(db.Model, Serializer):
    __tablename__ = 'diary_applications'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String, db.ForeignKey('users.discord_id', ondelete="CASCADE"))  # Cascade delete
    runescape_name = db.Column(db.String, nullable=False)
    diary_name = db.Column(db.String, nullable=False)
    diary_shorthand = db.Column(db.String, nullable=False)
    party = db.Column(ARRAY(db.String))
    party_ids = db.Column(ARRAY(db.String))
    time_split = db.Column(db.String)
    proof = db.Column(db.String)
    status = db.Column(db.String, default='Pending')
    target_diary_id = db.Column(UUID(as_uuid=True), db.ForeignKey('diary_content.id', ondelete="CASCADE"))  # Cascade delete
    verdict_reason = db.Column(db.Text)
    verdict_timestamp = db.Column(db.DateTime)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)
    
class DiaryCompletionLog(db.Model, Serializer):
    __tablename__ = 'diary_log'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String, db.ForeignKey('users.discord_id', ondelete="CASCADE"))  # Cascade delete
    diary_id = db.Column(UUID(as_uuid=True), db.ForeignKey('diary_content.id', ondelete="CASCADE"))  # Cascade delete
    diary_category_shorthand = db.Column(db.String)
    party = db.Column(ARRAY(db.String))
    party_ids = db.Column(ARRAY(db.String))
    proof = db.Column(db.String)
    points = db.Column(db.Integer, nullable=False)
    time_split = db.Column(db.String)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)

class ClanPointsLog(db.Model, Serializer):
    __tablename__ = 'clan_points_log'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String, db.ForeignKey('users.discord_id', ondelete="CASCADE"))  # Cascade delete
    points = db.Column(db.Numeric, nullable=False)
    tag = db.Column(db.String)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)


class RaidTierApplication(db.Model, Serializer):
    __tablename__ = 'raid_tier_application'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String, db.ForeignKey('users.discord_id', ondelete="CASCADE"))  # Cascade delete
    runescape_name = db.Column(db.String, nullable=False)
    proof = db.Column(db.String)
    status = db.Column(db.String, default='Pending')
    target_raid_tier_id = db.Column(UUID(as_uuid=True),
                                    db.ForeignKey('raid_tiers.id', ondelete="CASCADE"))  # Cascade delete
    verdict_reason = db.Column(db.Text)
    verdict_timestamp = db.Column(db.DateTime)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)

class RaidTierLog(db.Model, Serializer):
    __tablename__ = 'raid_tier_log'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.String, db.ForeignKey('users.discord_id', ondelete="CASCADE"))  # Cascade delete
    tier_name = db.Column(db.String, nullable=False)
    tier_order = db.Column(db.Integer, nullable=False)
    tier_points = db.Column(db.Integer, nullable=False)
    target_raid_tier_id = db.Column(UUID(as_uuid=True),
                                    db.ForeignKey('raid_tiers.id', ondelete="CASCADE"))  # Cascade delete
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)

class Events(db.Model, Serializer):
    __tablename__ = 'events'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = db.Column(db.String, nullable=False) # enum: "STABILITY_PARTY", "BINGO", "BOTW", "ROTW", "DINK_TEST"
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    image = db.Column(db.String)
    thread_id = db.Column(db.String)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))
    data = db.Column(JSONB, default={}) # Store additional data as JSONB for flexibility

    def serialize(self):
        return Serializer.serialize(self)
    
class EventTriggerMappings(db.Model, Serializer):
    __tablename__ = 'event_trigger_mappings'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = db.Column(UUID(as_uuid=True), db.ForeignKey('events.id', ondelete="CASCADE"), nullable=False)
    trigger_id = db.Column(UUID(as_uuid=True), db.ForeignKey('event_triggers.id', ondelete="CASCADE"), nullable=False)

    def serialize(self):
        return Serializer.serialize(self)
    
class EventTeams(db.Model, Serializer):
    __tablename__ = 'event_teams'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = db.Column(UUID(as_uuid=True), db.ForeignKey('events.id', ondelete="CASCADE"))  # Cascade delete
    name = db.Column(db.String, nullable=False)
    image = db.Column(db.String)
    captain = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete="CASCADE"))  # Cascade delete
    data = db.Column(JSONB, default={})

    def serialize(self):
        return Serializer.serialize(self)
    
class EventTeamMemberMappings(db.Model, Serializer):
    __tablename__ = 'event_team_member_mappings'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = db.Column(UUID(as_uuid=True), db.ForeignKey('events.id', ondelete="CASCADE"), nullable=False)
    team_id = db.Column(UUID(as_uuid=True), db.ForeignKey('event_teams.id', ondelete="CASCADE"), nullable=False)
    username = db.Column(db.String)
    discord_id = db.Column(db.String)

    def serialize(self):
        return Serializer.serialize(self)
    
class EventChallenges(db.Model, Serializer):
    __tablename__ = 'event_challenges'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = db.Column(db.String, nullable=False, default="OR") # enum: "OR", "AND", "CUMULATIVE"
    tasks = db.Column(ARRAY(db.String))
    value = db.Column(db.Integer, nullable=False, default=1)
    name = db.Column(db.String, default="")
    
    def serialize(self):
        return Serializer.serialize(self)
    
class EventTasks(db.Model, Serializer):
    __tablename__ = 'event_tasks'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    triggers = db.Column(ARRAY(db.String))
    quantity = db.Column(db.Integer, nullable=False, default=1)
    value = db.Column(db.Integer, nullable=False, default=1)
    
    def serialize(self):
        return Serializer.serialize(self)
    
class EventTriggers(db.Model, Serializer):
    __tablename__ = 'event_triggers'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trigger = db.Column(db.String, nullable=False)
    source = db.Column(db.String)
    type = db.Column(db.String, nullable=False, default="DROP") # enum: "DROP", "KC"
    
    def serialize(self):
        return Serializer.serialize(self)

class EventLog(db.Model, Serializer):
    __tablename__ = 'event_log'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = db.Column(UUID(as_uuid=True), db.ForeignKey('events.id', ondelete="CASCADE"))  # Cascade delete
    rsn = db.Column(db.String)
    discord_id = db.Column(db.String)
    trigger = db.Column(db.String, nullable=False)
    source = db.Column(db.String)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    type = db.Column(db.String, nullable=False) # enum: "DROP", "KC"
    value = db.Column(db.Integer, nullable=False, default=1)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc))

    def serialize(self):
        return Serializer.serialize(self)
    
    def __init__(self, event_id, rsn, discord_id, trigger, source, quantity, type, value):
        self.event_id = event_id
        self.rsn = rsn
        self.discord_id = discord_id
        self.trigger = trigger
        self.source = source
        self.quantity = quantity
        self.type = type
        self.value = value
        self.timestamp = datetime.datetime.now(datetime.timezone.utc)

    def to_dict(self):
        return {
            "id": str(self.id),
            "event_id": str(self.event_id),
            "rsn": self.rsn,
            "discord_id": self.discord_id,
            "trigger": self.trigger,
            "source": self.source,
            "quantity": self.quantity,
            "type": self.type,
            "value": self.value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
    