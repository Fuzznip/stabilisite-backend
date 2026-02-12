from app import app, db
from flask import request, jsonify
from models.new_events import Team, TeamMember, TileStatus, TaskStatus, ChallengeStatus, Tile, Task, Challenge, Trigger
from models.models import Users
from services.crud_service import CRUDService
from helper.helpers import ModelEncoder
import json
import logging

@app.route("/v2/teams", methods=['GET'])
def get_teams():
    """Get all teams with optional filtering by event"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    order_by = request.args.get('order_by', '-points')

    # Optional filters
    filters = {}
    if request.args.get('event_id'):
        filters['event_id'] = request.args.get('event_id')

    teams, total = CRUDService.get_all(Team, filters=filters, page=page, per_page=per_page, order_by=order_by)

    return jsonify({
        'data': [team.serialize() for team in teams],
        'total': total,
        'page': page,
        'per_page': per_page
    }), 200

@app.route("/v2/teams/<id>", methods=['GET'])
def get_team(id):
    """Get a single team by ID"""
    team = CRUDService.get_by_id(Team, id)
    if not team:
        return jsonify({'error': 'Team not found'}), 404

    return json.dumps(team.serialize(), cls=ModelEncoder), 200

@app.route("/v2/teams", methods=['POST'])
def create_team_v2():
    """Create a new team"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    # Validate required fields
    required_fields = ['event_id', 'name']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    team = CRUDService.create(Team, data)
    if not team:
        return jsonify({'error': 'Failed to create team (name may already exist for this event)'}), 500

    return json.dumps(team.serialize(), cls=ModelEncoder), 201

@app.route("/v2/teams/<id>", methods=['PUT'])
def update_team(id):
    """Update a team"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    team = CRUDService.update(Team, id, data)
    if not team:
        return jsonify({'error': 'Team not found or update failed'}), 404

    return json.dumps(team.serialize(), cls=ModelEncoder), 200

@app.route("/v2/teams/<id>", methods=['DELETE'])
def delete_team(id):
    """Delete a team"""
    success = CRUDService.delete(Team, id)
    if not success:
        return jsonify({'error': 'Team not found'}), 404

    return jsonify({'message': 'Team deleted successfully'}), 200

# =========================================
# TEAM MEMBER MANAGEMENT
# =========================================

@app.route("/v2/teams/<team_id>/members", methods=['GET'])
def get_team_members_v2(team_id):
    """Get all members of a team"""
    team = CRUDService.get_by_id(Team, team_id)
    if not team:
        return jsonify({'error': 'Team not found'}), 404

    members = TeamMember.query.filter_by(team_id=team_id).all()

    # Enrich with user data
    member_data = []
    for member in members:
        user = Users.query.filter_by(id=member.user_id).first()
        member_dict = member.serialize()
        if user:
            member_dict['user'] = {
                'id': str(user.id),
                'runescape_name': user.runescape_name,
                'discord_id': user.discord_id,
                'discord_avatar_url': user.discord_avatar_url
            }
        member_data.append(member_dict)

    return jsonify({
        'data': member_data,
        'total': len(member_data)
    }), 200

@app.route("/v2/teams/<team_id>/members", methods=['POST'])
def add_team_member(team_id):
    """Add a member to a team"""
    team = CRUDService.get_by_id(Team, team_id)
    if not team:
        return jsonify({'error': 'Team not found'}), 404

    data = request.get_json()
    if not data or 'user_id' not in data:
        return jsonify({'error': 'user_id is required'}), 400

    # Check if user exists
    user = Users.query.filter_by(discord_id=data['user_id']).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Check if user is already on another team in the same event
    existing_in_event = TeamMember.query.join(Team, TeamMember.team_id == Team.id).filter(
        Team.event_id == team.event_id,
        TeamMember.user_id == user.id
    ).first()
    if existing_in_event:
        return jsonify({'error': 'User is already on a team for this event'}), 400

    member_data = {
        'team_id': team_id,
        'user_id': user.id
    }
    member = CRUDService.create(TeamMember, member_data)
    if not member:
        return jsonify({'error': 'Failed to add team member'}), 500

    return json.dumps(member.serialize(), cls=ModelEncoder), 201

@app.route("/v2/teams/<team_id>/members/<user_id>", methods=['DELETE'])
def remove_team_member(team_id, user_id):
    """Remove a member from a team"""
    member = TeamMember.query.filter_by(team_id=team_id, user_id=user_id).first()
    if not member:
        return jsonify({'error': 'Team member not found'}), 404

    success = CRUDService.delete(TeamMember, member.id)
    if not success:
        return jsonify({'error': 'Failed to remove team member'}), 500

    return jsonify({'message': 'Team member removed successfully'}), 200

# =========================================
# TEAM PROGRESS
# =========================================

@app.route("/v2/teams/<team_id>/progress", methods=['GET'])
def get_team_progress(team_id):
    """
    Get complete progress for a team across all tiles.

    Optimized to use batch queries instead of N+1 queries.
    """
    team = Team.query.filter_by(id=team_id).first()
    if not team:
        return jsonify({'error': 'Team not found'}), 404

    # =========================================
    # BATCH FETCH ALL DATA UPFRONT
    # =========================================

    # Get all tiles for this event
    tiles = Tile.query.filter_by(event_id=team.event_id).order_by(Tile.index).all()
    tile_ids = [tile.id for tile in tiles]

    # Get all tasks for these tiles in one query
    all_tasks = Task.query.filter(Task.tile_id.in_(tile_ids)).all() if tile_ids else []
    task_ids = [task.id for task in all_tasks]

    # Get all challenges for these tasks in one query
    all_challenges = Challenge.query.filter(Challenge.task_id.in_(task_ids)).all() if task_ids else []
    challenge_ids = [c.id for c in all_challenges]

    # Get all triggers for challenges in one query
    trigger_ids = [c.trigger_id for c in all_challenges if c.trigger_id]
    all_triggers = Trigger.query.filter(Trigger.id.in_(trigger_ids)).all() if trigger_ids else []
    triggers_by_id = {t.id: t for t in all_triggers}

    # Get all tile statuses for this team in one query
    all_tile_statuses = TileStatus.query.filter(
        TileStatus.team_id == team_id,
        TileStatus.tile_id.in_(tile_ids)
    ).all() if tile_ids else []
    tile_statuses_by_tile = {ts.tile_id: ts for ts in all_tile_statuses}

    # Get all task statuses for this team in one query
    all_task_statuses = TaskStatus.query.filter(
        TaskStatus.team_id == team_id,
        TaskStatus.task_id.in_(task_ids)
    ).all() if task_ids else []
    task_statuses_by_task = {ts.task_id: ts for ts in all_task_statuses}

    # Get all challenge statuses for this team in one query
    all_challenge_statuses = ChallengeStatus.query.filter(
        ChallengeStatus.team_id == team_id,
        ChallengeStatus.challenge_id.in_(challenge_ids)
    ).all() if challenge_ids else []
    challenge_statuses_by_challenge = {cs.challenge_id: cs for cs in all_challenge_statuses}

    # Group tasks by tile for easier lookup
    tasks_by_tile = {}
    for task in all_tasks:
        if task.tile_id not in tasks_by_tile:
            tasks_by_tile[task.tile_id] = []
        tasks_by_tile[task.tile_id].append(task)

    # Group challenges by task for easier lookup
    challenges_by_task = {}
    for challenge in all_challenges:
        if challenge.task_id not in challenges_by_task:
            challenges_by_task[challenge.task_id] = []
        challenges_by_task[challenge.task_id].append(challenge)

    # =========================================
    # BUILD RESPONSE FROM IN-MEMORY DATA
    # =========================================

    progress_data = []
    for tile in tiles:
        tile_dict = tile.serialize()

        # Get tile status from lookup
        tile_status = tile_statuses_by_tile.get(tile.id)
        if tile_status:
            tile_dict['status'] = tile_status.serialize()
            tile_dict['status']['medal_level'] = tile_status.get_medal_level()
        else:
            tile_dict['status'] = {
                'tasks_completed': 0,
                'medal_level': 'none'
            }

        # Get tasks from lookup
        tasks_data = []
        for task in tasks_by_tile.get(tile.id, []):
            task_dict = task.serialize()

            # Get task status from lookup
            task_status = task_statuses_by_task.get(task.id)
            if task_status:
                task_dict['status'] = task_status.serialize()
            else:
                task_dict['status'] = {'completed': False}

            # Get challenges from lookup
            challenges_data = []
            for challenge in challenges_by_task.get(task.id, []):
                challenge_dict = challenge.serialize()

                # Get trigger from lookup
                if challenge.trigger_id and challenge.trigger_id in triggers_by_id:
                    challenge_dict['trigger'] = triggers_by_id[challenge.trigger_id].serialize()

                # Get challenge status from lookup
                challenge_status = challenge_statuses_by_challenge.get(challenge.id)
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

    return progress_data, 200
