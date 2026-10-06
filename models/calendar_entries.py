from app import db
from sqlalchemy.dialects.postgresql import UUID
from helper.helpers import Serializer
import uuid
import datetime

# Planned clan events for the home-page calendar. Deliberately separate from
# new_stability.events: several handlers pick "the" active event without a type
# filter, so a planning row there could hijack scoring.
CALENDAR_TYPES = ('bingo', 'conquest', 'botw', 'clog', 'adhoc')


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class CalendarEntry(db.Model, Serializer):
    __tablename__ = 'calendar_entries'
    __table_args__ = {'schema': 'new_stability'}

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    start_date = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    end_date = db.Column(db.DateTime(timezone=True), nullable=False)  # exclusive
    all_day = db.Column(db.Boolean, nullable=False, default=True)
    is_public = db.Column(db.Boolean, nullable=False, default=False)
    sync_discord = db.Column(db.Boolean, nullable=False, default=False)
    discord_event_id = db.Column(db.String(32), nullable=True)
    event_id = db.Column(UUID(as_uuid=True), db.ForeignKey('new_stability.events.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    def serialize(self):
        return Serializer.serialize(self)
