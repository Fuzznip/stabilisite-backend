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
    user = Users.query.filter_by(id=data['user_id']).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Check if already a member
    existing = TeamMember.query.filter_by(team_id=team_id, user_id=data['user_id']).first()
    if existing:
        return jsonify({'error': 'User is already a member of this team'}), 400

    member_data = {
        'team_id': team_id,
        'user_id': data['user_id']
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

    return progress_data, 200
