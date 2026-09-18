import json

from app import app, db
from flask import jsonify, request
from helper.helpers import ModelEncoder
from models.new_events import Challenge, ClogSlot, Event
from services.clog_service import (
    build_slots,
    delete_slot,
    event_slots,
    progress,
    recent_completions,
    serialize_slot,
    team_players,
)


def _require_clog_event(event_id):
    """Return (event, None) or (None, error_response)."""
    event = Event.query.get(event_id)
    if not event:
        return None, (jsonify({'error': 'Event not found'}), 404)
    if event.type != 'clog':
        return None, (jsonify({'error': 'Event is not a collection log race'}), 400)
    return event, None


@app.route('/v2/events/<event_id>/clog/slots', methods=['GET'])
def get_clog_slots(event_id):
    event, err = _require_clog_event(event_id)
    if err:
        return err

    rows = event_slots(event.id)
    return json.dumps({
        'data': [serialize_slot(slot, challenge) for slot, challenge in rows],
        'total': len(rows),
        'total_points': sum(int(c.value or 0) for _, c in rows),
    }, cls=ModelEncoder), 200


@app.route('/v2/events/<event_id>/clog/progress', methods=['GET'])
def get_clog_progress(event_id):
    event, err = _require_clog_event(event_id)
    if err:
        return err

    return json.dumps(progress(event.id), cls=ModelEncoder), 200


@app.route('/v2/events/<event_id>/clog/players', methods=['GET'])
def get_clog_players(event_id):
    """Each team's roster with the slots every player personally claimed.

    Players with nothing yet are included with an empty drop list — during a race
    the roster is as interesting as the scoreboard.
    """
    event, err = _require_clog_event(event_id)
    if err:
        return err

    return json.dumps({'data': team_players(event.id)}, cls=ModelEncoder), 200


@app.route('/v2/events/<event_id>/clog/recent', methods=['GET'])
def get_clog_recent(event_id):
    """Newest-first activity feed, optionally scoped to one team."""
    event, err = _require_clog_event(event_id)
    if err:
        return err

    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(100, max(1, request.args.get('per_page', 20, type=int)))
    team_id = request.args.get('team_id') or None

    return json.dumps(
        recent_completions(event.id, page=page, per_page=per_page, team_id=team_id),
        cls=ModelEncoder,
    ), 200


@app.route('/v2/events/<event_id>/clog/generate', methods=['POST'])
def generate_clog_slots(event_id):
    """Build the event's slots from the collection log catalog.

    Refuses an event that already has slots: generating twice would violate the
    (event_id, item_id) unique constraint halfway through and leave orphaned
    challenges behind. Delete the slots first if you really mean to regenerate.
    """
    event, err = _require_clog_event(event_id)
    if err:
        return err

    if ClogSlot.query.filter_by(event_id=event.id).first():
        return jsonify({'error': 'Event already has slots; delete them before regenerating'}), 409

    slots = build_slots(event.id)
    rows = event_slots(event.id)
    return json.dumps({
        'created': len(slots),
        'total_points': sum(int(c.value or 0) for _, c in rows),
    }, cls=ModelEncoder), 201


@app.route('/v2/clog/slots/<slot_id>', methods=['PUT'])
def update_clog_slot(slot_id):
    """Edit a slot's point value. Points live on the Challenge, not the slot."""
    slot = ClogSlot.query.get(slot_id)
    if not slot:
        return jsonify({'error': 'Slot not found'}), 404

    data = request.get_json()
    if not data or 'points' not in data:
        return jsonify({'error': 'points is required'}), 400
    if isinstance(data['points'], bool) or not isinstance(data['points'], int):
        return jsonify({'error': 'points must be an integer'}), 400

    challenge = Challenge.query.get(slot.challenge_id) if slot.challenge_id else None
    if not challenge:
        return jsonify({'error': 'Slot has no challenge'}), 409

    challenge.value = data['points']
    db.session.commit()

    return json.dumps(serialize_slot(slot, challenge), cls=ModelEncoder), 200


@app.route('/v2/clog/slots/<slot_id>', methods=['DELETE'])
def delete_clog_slot(slot_id):
    """Remove a slot from the event. This is the manual-pruning path."""
    slot = ClogSlot.query.get(slot_id)
    if not slot:
        return jsonify({'error': 'Slot not found'}), 404

    delete_slot(slot)
    return jsonify({'message': 'Slot deleted successfully'}), 200
