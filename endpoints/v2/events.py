from datetime import datetime, timezone
from app import app
from flask import request, jsonify
from models.new_events import Event
from services.crud_service import CRUDService
from helper.helpers import ModelEncoder
import json
import logging

@app.route("/v2/events", methods=['GET'])
def get_events_v2():
    """Get all events with optional filtering and pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    order_by = request.args.get('order_by', '-created_at')

    # Optional filters
    filters = {}
    if request.args.get('name'):
        filters['name'] = request.args.get('name')

    events, total = CRUDService.get_all(Event, filters=filters, page=page, per_page=per_page, order_by=order_by)

    return jsonify({
        'data': [event.serialize() for event in events],
        'total': total,
        'page': page,
        'per_page': per_page
    }), 200

@app.route("/v2/events/active", methods=['GET'])
def get_active_event():
    """Get the currently active bingo event with teams and tiles"""
    from models.new_events import Team, Tile, TeamMember
    from models.models import Users

    now = datetime.now(timezone.utc)
    event = Event.query.filter(
        Event.start_date <= now,
        Event.end_date >= now
    ).first()

    if not event:
        return jsonify({"error": "No active event"}), 404

    # Get related teams and tiles
    teams = Team.query.filter_by(event_id=event.id).order_by(Team.points.desc()).all()
    tiles = Tile.query.filter_by(event_id=event.id).order_by(Tile.index).all()

    response = event.serialize()

    # Serialize teams with member names
    teams_data = []
    for team in teams:
        team_dict = team.serialize()
        members = TeamMember.query.filter_by(team_id=team.id).all()
        team_dict['members'] = [
            Users.query.get(m.user_id).runescape_name
            for m in members
            if Users.query.get(m.user_id)
        ]
        teams_data.append(team_dict)

    response['teams'] = teams_data
    response['tiles'] = [tile.serialize() for tile in tiles]

    return json.dumps(response, cls=ModelEncoder), 200

@app.route("/v2/events/<id>", methods=['GET'])
def get_event(id):
    """Get a single event by ID"""
    from models.new_events import Team, Tile

    event = CRUDService.get_by_id(Event, id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    # Get related teams and tiles
    teams = Team.query.filter_by(event_id=id).order_by(Team.points.desc()).all()
    tiles = Tile.query.filter_by(event_id=id).order_by(Tile.index).all()

    response = event.serialize()
    response['teams'] = [team.serialize() for team in teams]
    response['tiles'] = [tile.serialize() for tile in tiles]

    return json.dumps(response, cls=ModelEncoder), 200


@app.route("/v2/events", methods=['POST'])
def create_event():
    """Create a new event"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    # Validate required fields
    required_fields = ['name', 'start_date', 'end_date']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    event = CRUDService.create(Event, data)
    if not event:
        return jsonify({'error': 'Failed to create event'}), 500

    return json.dumps(event.serialize(), cls=ModelEncoder), 201

@app.route("/v2/events/<id>", methods=['PUT'])
def update_event(id):
    """Update an event"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    event = CRUDService.update(Event, id, data)
    if not event:
        return jsonify({'error': 'Event not found or update failed'}), 404

    return json.dumps(event.serialize(), cls=ModelEncoder), 200

@app.route("/v2/events/<id>", methods=['DELETE'])
def delete_event(id):
    """Delete an event"""
    success = CRUDService.delete(Event, id)
    if not success:
        return jsonify({'error': 'Event not found'}), 404

    return jsonify({'message': 'Event deleted successfully'}), 200
