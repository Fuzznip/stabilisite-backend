from app import app
from flask import request, jsonify
from models.new_events import Action
from services.crud_service import CRUDService
from services.action_processor import ActionProcessor
from helper.helpers import ModelEncoder
import json
import logging
from datetime import datetime

@app.route("/v2/actions", methods=['GET'])
def get_actions():
    """Get all actions with optional filtering"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    order_by = request.args.get('order_by', '-date')

    # Optional filters
    filters = {}
    if request.args.get('player_id'):
        filters['player_id'] = request.args.get('player_id')
    if request.args.get('name'):
        filters['name'] = request.args.get('name')

    actions, total = CRUDService.get_all(Action, filters=filters, page=page, per_page=per_page, order_by=order_by)

    return jsonify({
        'data': [action.serialize() for action in actions],
        'total': total,
        'page': page,
        'per_page': per_page
    }), 200

@app.route("/v2/actions/<id>", methods=['GET'])
def get_action(id):
    """Get a single action by ID"""
    action = CRUDService.get_by_id(Action, id)
    if not action:
        return jsonify({'error': 'Action not found'}), 404

    return json.dumps(action.serialize(), cls=ModelEncoder), 200

@app.route("/v2/actions", methods=['POST'])
def create_action():
    """
    Create a new action and process it for active events

    Request body:
    {
        "player_id": "uuid",
        "name": "string",
        "type": "string" (optional, default 'DROP' - values: KC, DROP, QUEST, ACHIEVEMENT, DIARY, SKILL),
        "source": "string" (optional),
        "quantity": int (optional, default 1),
        "date": "ISO datetime" (optional, defaults to now)
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    # Validate required fields
    required_fields = ['player_id', 'name']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Set defaults
    if 'quantity' not in data:
        data['quantity'] = 1
    if 'type' not in data:
        data['type'] = 'DROP'

    # Validate action type
    valid_types = ['KC', 'DROP', 'QUEST', 'ACHIEVEMENT', 'DIARY', 'SKILL']
    if data['type'] not in valid_types:
        return jsonify({'error': f'Invalid type. Must be one of: {", ".join(valid_types)}'}), 400

    # Parse date if provided
    date = None
    if 'date' in data:
        try:
            date = datetime.fromisoformat(data['date'].replace('Z', '+00:00'))
        except Exception as e:
            return jsonify({'error': f'Invalid date format: {e}'}), 400

    # Process action through ActionProcessor
    # This creates the action AND processes it for all active events
    result = ActionProcessor.process_action(
        player_id=data['player_id'],
        action_name=data['name'],
        action_type=data['type'],
        source=data.get('source'),
        quantity=data['quantity'],
        date=date
    )

    return jsonify({
        'action_id': result['action_id'],
        'events_processed': result['events_processed'],
        'notifications': result['notifications']
    }), 201

@app.route("/v2/actions/<id>", methods=['DELETE'])
def delete_action(id):
    """Delete an action (also removes associated challenge proofs)"""
    success = CRUDService.delete(Action, id)
    if not success:
        return jsonify({'error': 'Action not found'}), 404

    return jsonify({'message': 'Action deleted successfully'}), 200
