from app import app
from flask import request, jsonify
from models.new_events import Tile, Task, Challenge, Trigger
from services.crud_service import CRUDService
from helper.helpers import ModelEncoder
import json
import logging

@app.route("/api/v2/tiles", methods=['GET'])
def get_tiles():
    """Get all tiles with optional filtering by event"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    order_by = request.args.get('order_by', 'index')

    # Optional filters
    filters = {}
    if request.args.get('event_id'):
        filters['event_id'] = request.args.get('event_id')

    tiles, total = CRUDService.get_all(Tile, filters=filters, page=page, per_page=per_page, order_by=order_by)

    return jsonify({
        'data': [tile.serialize() for tile in tiles],
        'total': total,
        'page': page,
        'per_page': per_page
    }), 200

@app.route("/api/v2/tiles/<id>", methods=['GET'])
def get_tile(id):
    """Get a single tile by ID with its tasks"""
    tile = CRUDService.get_by_id(Tile, id)
    if not tile:
        return jsonify({'error': 'Tile not found'}), 404

    # Enrich with tasks
    tile_data = tile.serialize()
    tasks = Task.query.filter_by(tile_id=id).all()
    tile_data['tasks'] = [task.serialize() for task in tasks]

    return json.dumps(tile_data, cls=ModelEncoder), 200

@app.route("/api/v2/tiles", methods=['POST'])
def create_tile():
    """Create a new tile"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    # Validate required fields
    required_fields = ['event_id', 'name', 'index']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    tile = CRUDService.create(Tile, data)
    if not tile:
        return jsonify({'error': 'Failed to create tile (index may already exist for this event)'}), 500

    return json.dumps(tile.serialize(), cls=ModelEncoder), 201

@app.route("/api/v2/tiles/<id>", methods=['PUT'])
def update_tile(id):
    """Update a tile"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    tile = CRUDService.update(Tile, id, data)
    if not tile:
        return jsonify({'error': 'Tile not found or update failed'}), 404

    return json.dumps(tile.serialize(), cls=ModelEncoder), 200

@app.route("/api/v2/tiles/<id>", methods=['DELETE'])
def delete_tile(id):
    """Delete a tile"""
    success = CRUDService.delete(Tile, id)
    if not success:
        return jsonify({'error': 'Tile not found'}), 404

    return jsonify({'message': 'Tile deleted successfully'}), 200

@app.route("/api/v2/tiles/<tile_id>/board", methods=['GET'])
def get_tile_board_data(tile_id):
    """Get complete tile data for board display including all tasks and challenges"""
    tile = CRUDService.get_by_id(Tile, tile_id)
    if not tile:
        return jsonify({'error': 'Tile not found'}), 404

    tile_data = tile.serialize()

    # Get all tasks for this tile
    tasks = Task.query.filter_by(tile_id=tile_id).all()
    tasks_data = []

    for task in tasks:
        task_dict = task.serialize()

        # Get all challenges for this task
        challenges = Challenge.query.filter_by(task_id=task.id).all()
        challenges_data = []

        for challenge in challenges:
            challenge_dict = challenge.serialize()

            # Get trigger info
            trigger = Trigger.query.filter_by(id=challenge.trigger_id).first()
            if trigger:
                challenge_dict['trigger'] = trigger.serialize()

            challenges_data.append(challenge_dict)

        task_dict['challenges'] = challenges_data
        tasks_data.append(task_dict)

    tile_data['tasks'] = tasks_data

    return json.dumps(tile_data, cls=ModelEncoder), 200
