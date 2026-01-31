from app import app
from flask import request, jsonify
from models.new_events import Tile, Task, Challenge, Trigger, Team, TileStatus, TaskStatus, ChallengeStatus, ChallengeProof, Action
from models.models import Users
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

        # Get all challenges for this task, ordered by ID (preserves creation order)
        challenges = Challenge.query.filter_by(task_id=task.id).order_by(Challenge.id).all()
        challenges_data = []

        for challenge in challenges:
            challenge_dict = challenge.serialize()

            # Get trigger info (only if challenge has a trigger)
            if challenge.trigger_id:
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
    """
    Get progress for a specific tile across all teams in the event.

    Optimized to use batch queries instead of N+1 queries.
    """
    tile = CRUDService.get_by_id(Tile, tile_id)
    if not tile:
        return jsonify({'error': 'Tile not found'}), 404

    # =========================================
    # BATCH FETCH ALL DATA UPFRONT
    # =========================================

    # Get all tasks for this tile
    tasks = Task.query.filter_by(tile_id=tile_id).order_by(Task.created_at).all()
    task_ids = [task.id for task in tasks]

    # Get all challenges for these tasks in one query
    all_challenges = Challenge.query.filter(Challenge.task_id.in_(task_ids)).order_by(Challenge.id).all()
    challenge_ids = [c.id for c in all_challenges]

    # Get all triggers for these challenges in one query
    trigger_ids = [c.trigger_id for c in all_challenges if c.trigger_id]
    all_triggers = Trigger.query.filter(Trigger.id.in_(trigger_ids)).all() if trigger_ids else []
    triggers_by_id = {t.id: t for t in all_triggers}

    # Get all teams for this event
    teams = Team.query.filter_by(event_id=tile.event_id).order_by(Team.points.desc()).all()
    team_ids = [team.id for team in teams]

    # Get all tile statuses in one query
    all_tile_statuses = TileStatus.query.filter(
        TileStatus.team_id.in_(team_ids),
        TileStatus.tile_id == tile_id
    ).all()
    tile_statuses_by_team = {ts.team_id: ts for ts in all_tile_statuses}

    # Get all task statuses in one query
    all_task_statuses = TaskStatus.query.filter(
        TaskStatus.team_id.in_(team_ids),
        TaskStatus.task_id.in_(task_ids)
    ).all()
    task_statuses_by_team_task = {(ts.team_id, ts.task_id): ts for ts in all_task_statuses}

    # Get all challenge statuses in one query
    all_challenge_statuses = ChallengeStatus.query.filter(
        ChallengeStatus.team_id.in_(team_ids),
        ChallengeStatus.challenge_id.in_(challenge_ids)
    ).all()
    challenge_statuses_by_team_challenge = {(cs.team_id, cs.challenge_id): cs for cs in all_challenge_statuses}
    challenge_status_ids = [cs.id for cs in all_challenge_statuses]

    # Get all proofs in one query
    all_proofs = ChallengeProof.query.filter(
        ChallengeProof.challenge_status_id.in_(challenge_status_ids)
    ).all() if challenge_status_ids else []
    proofs_by_challenge_status = {}
    for proof in all_proofs:
        if proof.challenge_status_id not in proofs_by_challenge_status:
            proofs_by_challenge_status[proof.challenge_status_id] = []
        proofs_by_challenge_status[proof.challenge_status_id].append(proof)

    # Get all actions for proofs in one query
    action_ids = [p.action_id for p in all_proofs if p.action_id]
    all_actions = Action.query.filter(Action.id.in_(action_ids)).all() if action_ids else []
    actions_by_id = {a.id: a for a in all_actions}

    # Get all players for actions in one query
    player_ids = [a.player_id for a in all_actions if a.player_id]
    all_players = Users.query.filter(Users.id.in_(player_ids)).all() if player_ids else []
    players_by_id = {p.id: p for p in all_players}

    # Group challenges by task for easier lookup
    challenges_by_task = {}
    for challenge in all_challenges:
        if challenge.task_id not in challenges_by_task:
            challenges_by_task[challenge.task_id] = []
        challenges_by_task[challenge.task_id].append(challenge)

    # =========================================
    # BUILD RESPONSE FROM IN-MEMORY DATA
    # =========================================

    # Build tile data with tasks and challenges
    tile_data = tile.serialize()
    tasks_data = []

    for task in tasks:
        task_dict = task.serialize()
        challenges_data = []

        for challenge in challenges_by_task.get(task.id, []):
            challenge_dict = challenge.serialize()
            if challenge.trigger_id and challenge.trigger_id in triggers_by_id:
                challenge_dict['trigger'] = triggers_by_id[challenge.trigger_id].serialize()
            challenges_data.append(challenge_dict)

        task_dict['challenges'] = challenges_data
        tasks_data.append(task_dict)

    tile_data['tasks'] = tasks_data

    # Build team progress data
    teams_progress = []

    for team in teams:
        team_dict = team.serialize()

        # Tile status
        tile_status = tile_statuses_by_team.get(team.id)
        if tile_status:
            team_dict['tile_status'] = tile_status.serialize()
            team_dict['tile_status']['medal_level'] = tile_status.get_medal_level()
        else:
            team_dict['tile_status'] = {'tasks_completed': 0, 'medal_level': 'none'}

        # Task statuses
        task_statuses = []
        for task in tasks:
            task_status = task_statuses_by_team_task.get((team.id, task.id))
            task_status_dict = {
                'task_id': str(task.id),
                'completed': task_status.completed if task_status else False
            }
            if task_status:
                task_status_dict['status_id'] = str(task_status.id)
            task_statuses.append(task_status_dict)
        team_dict['task_statuses'] = task_statuses

        # Challenge statuses
        challenge_statuses = []
        for task in tasks:
            for challenge in challenges_by_task.get(task.id, []):
                challenge_status = challenge_statuses_by_team_challenge.get((team.id, challenge.id))

                challenge_status_dict = {
                    'challenge_id': str(challenge.id),
                    'task_id': str(challenge.task_id),
                    'parent_challenge_id': str(challenge.parent_challenge_id) if challenge.parent_challenge_id else None,
                    'quantity': challenge_status.quantity if challenge_status else 0,
                    'required': challenge.quantity,
                    'completed': challenge_status.completed if challenge_status else False,
                    'require_all': challenge.require_all,
                    'value': challenge.value
                }

                # Add trigger details
                if challenge.trigger_id and challenge.trigger_id in triggers_by_id:
                    challenge_status_dict['trigger'] = triggers_by_id[challenge.trigger_id].serialize()

                if challenge_status:
                    challenge_status_dict['status_id'] = str(challenge_status.id)
                    challenge_status_dict['created_at'] = challenge_status.created_at.isoformat()
                    challenge_status_dict['updated_at'] = challenge_status.updated_at.isoformat()

                    # Build proofs with action details from in-memory data
                    proofs_data = []
                    for proof in proofs_by_challenge_status.get(challenge_status.id, []):
                        proof_dict = {
                            'id': str(proof.id),
                            'img_path': proof.img_path,
                            'created_at': proof.created_at.isoformat()
                        }
                        action = actions_by_id.get(proof.action_id)
                        if action:
                            proof_dict['action'] = {
                                'id': str(action.id),
                                'name': action.name,
                                'source': action.source,
                                'type': action.type,
                                'quantity': action.quantity,
                                'value': action.value,
                                'date': action.date.isoformat() if action.date else None
                            }
                            player = players_by_id.get(action.player_id)
                            if player:
                                proof_dict['action']['player'] = {
                                    'id': str(player.id),
                                    'runescape_name': player.runescape_name
                                }
                        proofs_data.append(proof_dict)
                    challenge_status_dict['proofs'] = proofs_data

                challenge_statuses.append(challenge_status_dict)

        team_dict['challenge_statuses'] = challenge_statuses
        teams_progress.append(team_dict)

    return jsonify({
        'tile': tile_data,
        'teams': teams_progress
    }), 200
