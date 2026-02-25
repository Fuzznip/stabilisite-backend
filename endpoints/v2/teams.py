from app import app, db
from flask import request, jsonify
from models.new_events import Team, TeamMember, TileStatus, Tile
from models.models import Users
from services.crud_service import CRUDService
from helper.helpers import ModelEncoder
import json
import uuid
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
    if not data or 'discord_id' not in data:
        return jsonify({'error': 'discord_id is required'}), 400

    # Check if user exists, create as guest if not
    user = Users.query.filter_by(discord_id=data['discord_id']).first()
    if not user:
        if 'username' not in data:
            return jsonify({'error': 'username is required when creating a new user'}), 400

        user = Users(
            id=uuid.uuid4(),
            discord_id=data['discord_id'],
            runescape_name=data['username'],
            is_member=False,
            rank='Guest',
            is_active=True
        )
        db.session.add(user)
        db.session.commit()

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
    Get lightweight progress for a team: points + medal level per tile.
    """
    team = Team.query.filter_by(id=team_id).first()
    if not team:
        return jsonify({'error': 'Team not found'}), 404

    tiles = Tile.query.filter_by(event_id=team.event_id).order_by(Tile.index).all()
    tile_ids = [tile.id for tile in tiles]

    tile_statuses = TileStatus.query.filter(
        TileStatus.team_id == team_id,
        TileStatus.tile_id.in_(tile_ids)
    ).all() if tile_ids else []
    tile_statuses_by_tile = {ts.tile_id: ts for ts in tile_statuses}

    tiles_data = []
    for tile in tiles:
        ts = tile_statuses_by_tile.get(tile.id)
        tiles_data.append({
            'index': tile.index,
            'tasks_completed': ts.tasks_completed if ts else 0
        })

    return jsonify({
        'points': team.points,
        'tiles': tiles_data
    }), 200
