from app import app
from flask import request, jsonify
from models.new_events import TileStatus, TaskStatus, ChallengeStatus, ChallengeProof, Team, Tile, Task, Challenge, Trigger
from helper.helpers import ModelEncoder
import json
import logging

# =========================================
# TILE STATUSES
# =========================================

@app.route("/api/v2/statuses/tiles", methods=['GET'])
def get_tile_statuses():
    """Get tile statuses with optional filtering"""
    team_id = request.args.get('team_id')
    tile_id = request.args.get('tile_id')

    query = TileStatus.query

    if team_id:
        query = query.filter_by(team_id=team_id)
    if tile_id:
        query = query.filter_by(tile_id=tile_id)

    statuses = query.all()

    return jsonify({
        'data': [status.serialize() for status in statuses],
        'total': len(statuses)
    }), 200

@app.route("/api/v2/statuses/tiles/<id>", methods=['GET'])
def get_tile_status(id):
    """Get a single tile status by ID"""
    status = TileStatus.query.filter_by(id=id).first()
    if not status:
        return jsonify({'error': 'Tile status not found'}), 404

    status_data = status.serialize()
    status_data['medal_level'] = status.get_medal_level()

    return json.dumps(status_data, cls=ModelEncoder), 200

# =========================================
# TASK STATUSES
# =========================================

@app.route("/api/v2/statuses/tasks", methods=['GET'])
def get_task_statuses():
    """Get task statuses with optional filtering"""
    team_id = request.args.get('team_id')
    task_id = request.args.get('task_id')

    query = TaskStatus.query

    if team_id:
        query = query.filter_by(team_id=team_id)
    if task_id:
        query = query.filter_by(task_id=task_id)

    statuses = query.all()

    return jsonify({
        'data': [status.serialize() for status in statuses],
        'total': len(statuses)
    }), 200

# =========================================
# CHALLENGE STATUSES
# =========================================

@app.route("/api/v2/statuses/challenges", methods=['GET'])
def get_challenge_statuses():
    """Get challenge statuses with optional filtering"""
    team_id = request.args.get('team_id')
    challenge_id = request.args.get('challenge_id')

    query = ChallengeStatus.query

    if team_id:
        query = query.filter_by(team_id=team_id)
    if challenge_id:
        query = query.filter_by(challenge_id=challenge_id)

    statuses = query.all()

    # Enrich with challenge and proof data
    enriched_statuses = []
    for status in statuses:
        status_dict = status.serialize()

        # Add challenge info
        challenge = Challenge.query.filter_by(id=status.challenge_id).first()
        if challenge:
            status_dict['challenge'] = challenge.serialize()

            # Add trigger info to challenge
            trigger = Trigger.query.filter_by(id=challenge.trigger_id).first()
            if trigger:
                status_dict['challenge']['trigger'] = trigger.serialize()

        # Add proof count
        proof_count = ChallengeProof.query.filter_by(challenge_status_id=status.id).count()
        status_dict['proof_count'] = proof_count

        enriched_statuses.append(status_dict)

    return jsonify({
        'data': enriched_statuses,
        'total': len(enriched_statuses)
    }), 200

# =========================================
# TEAM PROGRESS
# =========================================

@app.route("/api/v2/teams/<team_id>/progress", methods=['GET'])
def get_team_progress(team_id):
    """Get complete progress for a team across all tiles"""
    team = Team.query.filter_by(id=team_id).first()
    if not team:
        return jsonify({'error': 'Team not found'}), 404

    # Get all tiles for this event
    tiles = Tile.query.filter_by(event_id=team.event_id).order_by(Tile.index).all()

    progress_data = []
    for tile in tiles:
        tile_dict = tile.serialize()

        # Get tile status
        tile_status = TileStatus.query.filter_by(team_id=team_id, tile_id=tile.id).first()
        if tile_status:
            tile_dict['status'] = tile_status.serialize()
            tile_dict['status']['medal_level'] = tile_status.get_medal_level()
        else:
            tile_dict['status'] = {
                'tasks_completed': 0,
                'medal_level': 'none'
            }

        # Get tasks for this tile
        tasks = Task.query.filter_by(tile_id=tile.id).all()
        tasks_data = []

        for task in tasks:
            task_dict = task.serialize()

            # Get task status
            task_status = TaskStatus.query.filter_by(team_id=team_id, task_id=task.id).first()
            if task_status:
                task_dict['status'] = task_status.serialize()
            else:
                task_dict['status'] = {'completed': False}

            # Get challenges for this task
            challenges = Challenge.query.filter_by(task_id=task.id).all()
            challenges_data = []

            for challenge in challenges:
                challenge_dict = challenge.serialize()

                # Get trigger
                trigger = Trigger.query.filter_by(id=challenge.trigger_id).first()
                if trigger:
                    challenge_dict['trigger'] = trigger.serialize()

                # Get challenge status
                challenge_status = ChallengeStatus.query.filter_by(team_id=team_id, challenge_id=challenge.id).first()
                if challenge_status:
                    challenge_dict['status'] = challenge_status.serialize()
                else:
                    challenge_dict['status'] = {
                        'quantity': 0,
                        'completed': False
                    }

                challenges_data.append(challenge_dict)

            task_dict['challenges'] = challenges_data
            tasks_data.append(task_dict)

        tile_dict['tasks'] = tasks_data
        progress_data.append(tile_dict)

    return jsonify({
        'team': team.serialize(),
        'tiles': progress_data
    }), 200

# =========================================
# CHALLENGE PROOFS
# =========================================

@app.route("/api/v2/statuses/challenges/<challenge_status_id>/proofs", methods=['GET'])
def get_challenge_proofs(challenge_status_id):
    """Get all proofs for a specific challenge status"""
    challenge_status = ChallengeStatus.query.filter_by(id=challenge_status_id).first()
    if not challenge_status:
        return jsonify({'error': 'Challenge status not found'}), 404

    proofs = ChallengeProof.query.filter_by(challenge_status_id=challenge_status_id).all()

    return jsonify({
        'data': [proof.serialize() for proof in proofs],
        'total': len(proofs)
    }), 200
