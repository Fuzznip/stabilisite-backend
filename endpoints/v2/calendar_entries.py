import logging
import uuid
from datetime import datetime, timedelta, timezone

from app import app, db
from flask import jsonify, request
from helper import discord_helper
from models.calendar_entries import CALENDAR_TYPES, CalendarEntry
from models.new_events import Event


# Discord rejects scheduled-event names over 100 characters, and a synced entry
# with a longer name would fail on every save.
MAX_NAME_LENGTH = 100


def _parse_datetime(value):
    """An ISO 8601 string with an explicit offset, as UTC. Naive times are rejected:
    the site converts ET to UTC before sending, so a bare time means a bug."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _parse_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _validate(data):
    """Return (fields, None) or (None, error message)."""
    if not isinstance(data, dict):
        return None, 'No JSON received'

    name = (data.get('name') or '').strip()
    if not name:
        return None, 'Name is required'
    if len(name) > MAX_NAME_LENGTH:
        return None, f'Name must be {MAX_NAME_LENGTH} characters or fewer'

    if data.get('type') not in CALENDAR_TYPES:
        return None, f"Type must be one of: {', '.join(CALENDAR_TYPES)}"

    start = _parse_datetime(data.get('start_date'))
    end = _parse_datetime(data.get('end_date'))
    if not start or not end:
        return None, 'start_date and end_date must be ISO datetimes with a timezone'
    if end <= start:
        return None, 'end_date must be after start_date'

    event_id = None
    if data.get('event_id'):
        event_id = _parse_uuid(data['event_id'])
        if not event_id or not Event.query.get(event_id):
            return None, 'Linked event not found'

    return {
        'name': name,
        'type': data['type'],
        'start_date': start,
        'end_date': end,
        'all_day': bool(data.get('all_day', True)),
        'is_public': bool(data.get('is_public', False)),
        'sync_discord': bool(data.get('sync_discord', False)),
        'event_id': event_id,
    }, None


def _get_entry(entry_id):
    parsed = _parse_uuid(entry_id)
    return CalendarEntry.query.get(parsed) if parsed else None


# Discord refuses a start time in the past; the entry itself keeps its real start.
DISCORD_START_LEAD = timedelta(minutes=1)


def _discord_window(entry):
    start = max(entry.start_date, datetime.now(timezone.utc) + DISCORD_START_LEAD)
    return start, entry.end_date


def _create_discord_event(entry, start, end):
    new_id = discord_helper.create_discord_scheduled_event(entry.name, start, end)
    if not new_id:
        return 'failed'
    entry.discord_event_id = new_id
    db.session.commit()
    return 'ok'


def _sync_discord(entry):
    """Mirror a saved entry onto Discord. Returns 'ok', 'failed' or 'skipped'.

    Never raises: a Discord problem must not undo the save. A failed create leaves
    discord_event_id empty so the next save retries.
    """
    if not discord_helper.discord_sync_enabled():
        return 'skipped'

    if not entry.sync_discord:
        if not entry.discord_event_id:
            return 'skipped'
        deleted = discord_helper.delete_discord_scheduled_event(entry.discord_event_id)
        if not deleted:
            logging.error(f"Calendar entry {entry.id}: Discord event {entry.discord_event_id} orphaned")
        # Cleared either way: sync is off, so the site no longer owns that event.
        entry.discord_event_id = None
        db.session.commit()
        return 'ok' if deleted else 'failed'

    start, end = _discord_window(entry)
    if end <= start:
        return 'skipped'  # already over; Discord would reject it

    if entry.discord_event_id:
        result = discord_helper.update_discord_scheduled_event(entry.discord_event_id, entry.name, start, end)
        if result == 'missing':  # deleted by hand in Discord
            return _create_discord_event(entry, start, end)
        return result

    return _create_discord_event(entry, start, end)


@app.route("/v2/calendar", methods=['GET'])
def get_calendar_entries():
    """Entries overlapping [from, to). Private entries only with include_private=true."""
    start = _parse_datetime(request.args.get('from'))
    end = _parse_datetime(request.args.get('to'))
    if not start or not end or end <= start:
        return jsonify({'error': 'from and to must be ISO datetimes with a timezone, from before to'}), 400

    query = CalendarEntry.query.filter(CalendarEntry.start_date < end, CalendarEntry.end_date > start)
    if request.args.get('include_private', '').lower() != 'true':
        query = query.filter(CalendarEntry.is_public.is_(True))

    entries = query.order_by(CalendarEntry.start_date).all()
    return jsonify({'data': [entry.serialize() for entry in entries]}), 200


@app.route("/v2/calendar", methods=['POST'])
def create_calendar_entry():
    fields, error = _validate(request.get_json(silent=True))
    if error:
        return jsonify({'error': error}), 400

    entry = CalendarEntry(**fields)
    db.session.add(entry)
    db.session.commit()

    discord_sync = _sync_discord(entry)
    return jsonify({'data': entry.serialize(), 'discord_sync': discord_sync}), 201


@app.route("/v2/calendar/<entry_id>", methods=['PUT'])
def update_calendar_entry(entry_id):
    entry = _get_entry(entry_id)
    if not entry:
        return jsonify({'error': 'Calendar entry not found'}), 404

    fields, error = _validate(request.get_json(silent=True))
    if error:
        return jsonify({'error': error}), 400

    for key, value in fields.items():
        setattr(entry, key, value)
    db.session.commit()

    discord_sync = _sync_discord(entry)
    return jsonify({'data': entry.serialize(), 'discord_sync': discord_sync}), 200


@app.route("/v2/calendar/<entry_id>", methods=['DELETE'])
def delete_calendar_entry(entry_id):
    entry = _get_entry(entry_id)
    if not entry:
        return jsonify({'error': 'Calendar entry not found'}), 404

    discord_event_id = entry.discord_event_id
    db.session.delete(entry)
    db.session.commit()

    if not discord_event_id or not discord_helper.discord_sync_enabled():
        return jsonify({'discord_sync': 'skipped'}), 200
    deleted = discord_helper.delete_discord_scheduled_event(discord_event_id)
    if not deleted:
        logging.error(f"Deleted calendar entry {entry_id}: Discord event {discord_event_id} orphaned")
    return jsonify({'discord_sync': 'ok' if deleted else 'failed'}), 200
