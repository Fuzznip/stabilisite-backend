from app import app
from flask import request, jsonify
from models.new_events import Trigger
from services.crud_service import CRUDService
from helper.helpers import ModelEncoder
import json
import logging

@app.route("/v2/triggers", methods=['GET'])
def get_triggers():
    """Get all triggers with optional filtering"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    order_by = request.args.get('order_by', 'name')

    # Optional filters
    filters = {}
    if request.args.get('type'):
        filters['type'] = request.args.get('type')
    if request.args.get('source'):
        filters['source'] = request.args.get('source')

    triggers, total = CRUDService.get_all(Trigger, filters=filters, page=page, per_page=per_page, order_by=order_by)

    return jsonify({
        'data': [trigger.serialize() for trigger in triggers],
        'total': total,
        'page': page,
        'per_page': per_page
    }), 200

@app.route("/v2/triggers/<id>", methods=['GET'])
def get_trigger(id):
    """Get a single trigger by ID"""
    trigger = CRUDService.get_by_id(Trigger, id)
    if not trigger:
        return jsonify({'error': 'Trigger not found'}), 404

    return json.dumps(trigger.serialize(), cls=ModelEncoder), 200

@app.route("/v2/triggers", methods=['POST'])
def create_trigger():
    """Create a new trigger"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    # Validate required fields
    required_fields = ['name']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Set default type if not provided
    if 'type' not in data:
        data['type'] = 'DROP'

    trigger = CRUDService.create(Trigger, data)
    if not trigger:
        return jsonify({'error': 'Failed to create trigger (name+source combo may already exist)'}), 500

    return json.dumps(trigger.serialize(), cls=ModelEncoder), 201

@app.route("/v2/triggers/<id>", methods=['PUT'])
def update_trigger(id):
    """Update a trigger"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    trigger = CRUDService.update(Trigger, id, data)
    if not trigger:
        return jsonify({'error': 'Trigger not found or update failed'}), 404

    return json.dumps(trigger.serialize(), cls=ModelEncoder), 200

@app.route("/v2/triggers/<id>", methods=['DELETE'])
def delete_trigger(id):
    """Delete a trigger"""
    success = CRUDService.delete(Trigger, id)
    if not success:
        return jsonify({'error': 'Trigger not found or in use by challenges'}), 404

    return jsonify({'message': 'Trigger deleted successfully'}), 200

@app.route("/v2/triggers/search", methods=['GET'])
def search_triggers():
    """Search triggers by name (partial match)"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Query parameter "q" is required'}), 400

    triggers = Trigger.query.filter(Trigger.name.ilike(f'%{query}%')).limit(50).all()

    return jsonify({
        'data': [trigger.serialize() for trigger in triggers],
        'total': len(triggers)
    }), 200
