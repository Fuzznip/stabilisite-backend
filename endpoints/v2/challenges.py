from app import app
from flask import request, jsonify
from models.new_events import Challenge
from services.crud_service import CRUDService
from helper.helpers import ModelEncoder
import json
import logging

@app.route("/v2/challenges", methods=['GET'])
def get_challenges():
    """Get all challenges with optional filtering by task"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)

    # Optional filters
    filters = {}
    if request.args.get('task_id'):
        filters['task_id'] = request.args.get('task_id')
    if request.args.get('trigger_id'):
        filters['trigger_id'] = request.args.get('trigger_id')

    challenges, total = CRUDService.get_all(Challenge, filters=filters, page=page, per_page=per_page)

    return jsonify({
        'data': [challenge.serialize() for challenge in challenges],
        'total': total,
        'page': page,
        'per_page': per_page
    }), 200

@app.route("/v2/challenges/<id>", methods=['GET'])
def get_challenge(id):
    """Get a single challenge by ID"""
    challenge = CRUDService.get_by_id(Challenge, id)
    if not challenge:
        return jsonify({'error': 'Challenge not found'}), 404

    # Enrich with children if it's a parent challenge
    challenge_data = challenge.serialize()
    if challenge.children:
        challenge_data['children'] = [child.serialize() for child in challenge.children]

    return json.dumps(challenge_data, cls=ModelEncoder), 200

@app.route("/v2/challenges", methods=['POST'])
def create_challenge():
    """Create a new challenge"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    # Validate required fields
    required_fields = ['task_id', 'trigger_id']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Set defaults
    if 'require_all' not in data:
        data['require_all'] = False
    if 'quantity' not in data:
        data['quantity'] = 1

    challenge = CRUDService.create(Challenge, data)
    if not challenge:
        return jsonify({'error': 'Failed to create challenge'}), 500

    return json.dumps(challenge.serialize(), cls=ModelEncoder), 201

@app.route("/v2/challenges/<id>", methods=['PUT'])
def update_challenge(id):
    """Update a challenge"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    challenge = CRUDService.update(Challenge, id, data)
    if not challenge:
        return jsonify({'error': 'Challenge not found or update failed'}), 404

    return json.dumps(challenge.serialize(), cls=ModelEncoder), 200

@app.route("/v2/challenges/<id>", methods=['DELETE'])
def delete_challenge(id):
    """Delete a challenge"""
    success = CRUDService.delete(Challenge, id)
    if not success:
        return jsonify({'error': 'Challenge not found'}), 404

    return jsonify({'message': 'Challenge deleted successfully'}), 200

@app.route("/v2/challenges/<id>/tree", methods=['GET'])
def get_challenge_tree(id):
    """Get complete challenge tree (parent and all descendants)"""
    challenge = CRUDService.get_by_id(Challenge, id)
    if not challenge:
        return jsonify({'error': 'Challenge not found'}), 404

    def build_tree(c):
        """Recursively build challenge tree"""
        node = c.serialize()
        if c.children:
            node['children'] = [build_tree(child) for child in c.children]
        return node

    tree = build_tree(challenge)
    return json.dumps(tree, cls=ModelEncoder), 200
