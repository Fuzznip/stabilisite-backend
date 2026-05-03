import json
import logging
import queue

from app import app, db
from flask import Response, jsonify, request, stream_with_context
from helper.helpers import ModelEncoder
from models.new_events import Event, EventLog, Region, Territory
from services.conquest_service import sse_clients


def _require_conquest_event(event_id):
    """Return (event, None) or (None, error_response)."""
    event = Event.query.get(event_id)
    if not event:
        return None, (jsonify({'error': 'Event not found'}), 404)
    if event.type != 'conquest':
        return None, (jsonify({'error': 'Event is not a conquest event'}), 400)
    return event, None


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/regions', methods=['GET'])
def get_conquest_regions(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    regions = Region.query.filter_by(event_id=event_id).all()
    return jsonify({'data': [r.serialize() for r in regions]}), 200


@app.route('/v2/events/<event_id>/regions', methods=['POST'])
def create_conquest_region(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400
    if 'name' not in data:
        return jsonify({'error': 'Missing required field: name'}), 400

    region = Region(
        event_id=event_id,
        name=data['name'],
        image_url=data.get('image_url'),
        offset_x=data.get('offset_x'),
        offset_y=data.get('offset_y'),
    )
    db.session.add(region)
    db.session.commit()
    return json.dumps(region.serialize(), cls=ModelEncoder), 201


# ---------------------------------------------------------------------------
# Territories
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/territories', methods=['GET'])
def get_conquest_territories(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    regions = Region.query.filter_by(event_id=event_id).with_entities(Region.id).all()
    region_ids = [r.id for r in regions]

    territories = Territory.query.filter(
        Territory.region_id.in_(region_ids)
    ).order_by(Territory.display_order).all() if region_ids else []

    return jsonify({'data': [t.serialize() for t in territories]}), 200


@app.route('/v2/regions/<region_id>/territories', methods=['POST'])
def create_conquest_territory(region_id):
    region = Region.query.get(region_id)
    if not region:
        return jsonify({'error': 'Region not found'}), 404

    _, err = _require_conquest_event(str(region.event_id))
    if err:
        return err

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400
    if 'name' not in data:
        return jsonify({'error': 'Missing required field: name'}), 400

    territory = Territory(
        region_id=region_id,
        name=data['name'],
        tier=data.get('tier'),
        challenge_id=data.get('challenge_id'),
        display_order=data.get('display_order'),
        offset_x=data.get('offset_x'),
        offset_y=data.get('offset_y'),
        polygon_points=data.get('polygon_points'),
    )
    db.session.add(territory)
    db.session.commit()
    return json.dumps(territory.serialize(), cls=ModelEncoder), 201


@app.route('/v2/territories/<territory_id>', methods=['PUT'])
def update_conquest_territory(territory_id):
    territory = Territory.query.get(territory_id)
    if not territory:
        return jsonify({'error': 'Territory not found'}), 404

    region = Region.query.get(territory.region_id)
    _, err = _require_conquest_event(str(region.event_id))
    if err:
        return err

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    updatable = ('name', 'tier', 'challenge_id', 'display_order', 'offset_x', 'offset_y', 'polygon_points')
    for field in updatable:
        if field in data:
            setattr(territory, field, data[field])

    db.session.commit()
    return json.dumps(territory.serialize(), cls=ModelEncoder), 200


# ---------------------------------------------------------------------------
# Event Logs
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/event-logs', methods=['GET'])
def get_conquest_event_logs(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    pagination = (
        EventLog.query
        .filter_by(event_id=event_id)
        .order_by(EventLog.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify({
        'data': [log.serialize() for log in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
    }), 200


# ---------------------------------------------------------------------------
# SSE Scoreboard Stream
# ---------------------------------------------------------------------------

@app.route('/v2/events/<event_id>/scoreboard/stream', methods=['GET'])
def conquest_scoreboard_stream(event_id):
    event, err = _require_conquest_event(event_id)
    if err:
        return err

    def generate():
        q = queue.SimpleQueue()
        event_clients = sse_clients.setdefault(str(event_id), set())
        event_clients.add(q)
        try:
            # Initial snapshot: last 10 log entries, oldest first
            logs = (
                EventLog.query
                .filter_by(event_id=event_id)
                .order_by(EventLog.created_at.desc())
                .limit(10)
                .all()
            )
            logs.reverse()
            if logs:
                payload = json.dumps([log.serialize() for log in logs])
                yield f"data: {payload}\n\n"

            while True:
                try:
                    data = q.get(timeout=30)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        except GeneratorExit:
            pass
        finally:
            event_clients.discard(q)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )
