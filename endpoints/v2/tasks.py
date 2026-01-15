from app import app
from flask import request, jsonify
from models.new_events import Task, Challenge
from services.crud_service import CRUDService
from helper.helpers import ModelEncoder
import json
import logging

@app.route("/v2/tasks", methods=['GET'])
def get_tasks():
    """Get all tasks with optional filtering by tile"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)

    # Optional filters
    filters = {}
    if request.args.get('tile_id'):
        filters['tile_id'] = request.args.get('tile_id')

    tasks, total = CRUDService.get_all(Task, filters=filters, page=page, per_page=per_page)

    return jsonify({
        'data': [task.serialize() for task in tasks],
        'total': total,
        'page': page,
        'per_page': per_page
    }), 200

@app.route("/v2/tasks/<id>", methods=['GET'])
def get_task(id):
    """Get a single task by ID"""
    task = CRUDService.get_by_id(Task, id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    return json.dumps(task.serialize(), cls=ModelEncoder), 200

@app.route("/v2/tasks", methods=['POST'])
def create_task():
    """Create a new task"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    # Validate required fields
    required_fields = ['tile_id', 'name']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Set default require_all if not provided
    if 'require_all' not in data:
        data['require_all'] = False

    task = CRUDService.create(Task, data)
    if not task:
        return jsonify({'error': 'Failed to create task'}), 500

    return json.dumps(task.serialize(), cls=ModelEncoder), 201

@app.route("/v2/tasks/<id>", methods=['PUT'])
def update_task(id):
    """Update a task"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    task = CRUDService.update(Task, id, data)
    if not task:
        return jsonify({'error': 'Task not found or update failed'}), 404

    return json.dumps(task.serialize(), cls=ModelEncoder), 200

@app.route("/v2/tasks/<id>", methods=['DELETE'])
def delete_task(id):
    """Delete a task"""
    success = CRUDService.delete(Task, id)
    if not success:
        return jsonify({'error': 'Task not found'}), 404

    return jsonify({'message': 'Task deleted successfully'}), 200
