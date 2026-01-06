from app import app
from flask import request, jsonify
from models.new_events import Tile, Task, Challenge, Trigger, Team, TileStatus, TaskStatus, ChallengeStatus
from services.crud_service import CRUDService
from helper.helpers import ModelEncoder
import json
import logging

@app.route("/v2/tiles", methods=['GET'])
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

@app.route("/v2/tiles/<id>", methods=['GET'])
def get_tile(id):
    """Get a single tile by ID with its tasks, challenges, and triggers"""
    tile = CRUDService.get_by_id(Tile, id)
    if not tile:
        return jsonify({'error': 'Tile not found'}), 404

    tile_data = tile.serialize()

    # Get all tasks for this tile
    tasks = Task.query.filter_by(tile_id=id).all()
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

@app.route("/v2/tiles", methods=['POST'])
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

@app.route("/v2/tiles/<id>", methods=['PUT'])
def update_tile(id):
    """Update a tile"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    tile = CRUDService.update(Tile, id, data)
    if not tile:
        return jsonify({'error': 'Tile not found or update failed'}), 404

    return json.dumps(tile.serialize(), cls=ModelEncoder), 200

@app.route("/v2/tiles/<id>", methods=['DELETE'])
def delete_tile(id):
    """Delete a tile"""
    success = CRUDService.delete(Tile, id)
    if not success:
        return jsonify({'error': 'Tile not found'}), 404

    return jsonify({'message': 'Tile deleted successfully'}), 200

# =========================================
# TILE PROGRESS
# =========================================

@app.route("/v2/tiles/<tile_id>/progress", methods=['GET'])
def get_tile_progress(tile_id):
    """Get progress for a specific tile across all teams in the event"""
    tile = CRUDService.get_by_id(Tile, tile_id)
    if not tile:
        return jsonify({'error': 'Tile not found'}), 404

    # Get tile data with tasks and challenges
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

    # Get all teams for this event
    teams = Team.query.filter_by(event_id=tile.event_id).order_by(Team.points.desc()).all()
    teams_progress = []

    for team in teams:
        team_dict = team.serialize()

        # Get tile status for this team
        tile_status = TileStatus.query.filter_by(team_id=team.id, tile_id=tile_id).first()
        if tile_status:
            team_dict['tile_status'] = tile_status.serialize()
            team_dict['tile_status']['medal_level'] = tile_status.get_medal_level()
        else:
            team_dict['tile_status'] = {
                'tasks_completed': 0,
                'medal_level': 'none'
            }

        # Get task statuses for this team and tile
        task_statuses = []
        for task in tasks:
            task_status = TaskStatus.query.filter_by(team_id=team.id, task_id=task.id).first()
            task_status_dict = {
                'task_id': str(task.id),
                'completed': task_status.completed if task_status else False
            }
            if task_status:
                task_status_dict['status_id'] = str(task_status.id)
            task_statuses.append(task_status_dict)

        team_dict['task_statuses'] = task_statuses

        # Get challenge statuses for this team and tile
        challenge_statuses = []
        for task in tasks:
            challenges = Challenge.query.filter_by(task_id=task.id).all()
            for challenge in challenges:
                challenge_status = ChallengeStatus.query.filter_by(team_id=team.id, challenge_id=challenge.id).first()
                challenge_status_dict = {
                    'challenge_id': str(challenge.id),
                    'quantity': challenge_status.quantity if challenge_status else 0,
                    'completed': challenge_status.completed if challenge_status else False
                }
                if challenge_status:
                    challenge_status_dict['status_id'] = str(challenge_status.id)
                challenge_statuses.append(challenge_status_dict)

        team_dict['challenge_statuses'] = challenge_statuses

        teams_progress.append(team_dict)

    return jsonify({
        'tile': tile_data,
        'teams': teams_progress
    }), 200
