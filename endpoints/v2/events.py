from datetime import datetime, timezone
from app import app, db
from flask import request, jsonify
from models.new_events import Event, DailyRiddle, DailyRiddleSolution, TeamMember
from models.models import Users
from services.crud_service import CRUDService
from helper.helpers import ModelEncoder
import json
import logging

@app.route("/v2/events", methods=['GET'])
def get_events_v2():
    """Get all events with optional filtering and pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    order_by = request.args.get('order_by', '-created_at')

    # Optional filters
    filters = {}
    if request.args.get('name'):
        filters['name'] = request.args.get('name')

    events, total = CRUDService.get_all(Event, filters=filters, page=page, per_page=per_page, order_by=order_by)

    return jsonify({
        'data': [event.serialize() for event in events],
        'total': total,
        'page': page,
        'per_page': per_page
    }), 200

@app.route("/v2/events/active", methods=['GET'])
def get_active_event():
    """Get the currently active bingo event with teams and tiles"""
    from models.new_events import Team, Tile, TeamMember
    from models.models import Users

    now = datetime.now(timezone.utc)
    event = Event.query.filter(
        Event.start_date <= now,
        Event.end_date >= now
    ).first()

    if not event:
        return jsonify({"error": "No active event"}), 404

    # Get related teams and tiles
    teams = Team.query.filter_by(event_id=event.id).order_by(Team.points.desc()).all()
    tiles = Tile.query.filter_by(event_id=event.id).order_by(Tile.index).all()

    response = event.serialize()

    # Batch fetch all team members for all teams in one query
    team_ids = [team.id for team in teams]
    all_members = TeamMember.query.filter(TeamMember.team_id.in_(team_ids)).all() if team_ids else []

    # Batch fetch all users for those members in one query
    user_ids = list(set(m.user_id for m in all_members))
    all_users = Users.query.filter(Users.id.in_(user_ids)).all() if user_ids else []
    users_by_id = {user.id: user for user in all_users}

    # Group members by team_id
    members_by_team = {}
    for member in all_members:
        if member.team_id not in members_by_team:
            members_by_team[member.team_id] = []
        members_by_team[member.team_id].append(member)

    # Serialize teams with member names
    teams_data = []
    for team in teams:
        team_dict = team.serialize()
        team_members = members_by_team.get(team.id, [])
        team_dict['members'] = [
            users_by_id[m.user_id].runescape_name
            for m in team_members
            if m.user_id in users_by_id
        ]
        teams_data.append(team_dict)

    response['teams'] = teams_data
    response['tiles'] = [tile.serialize() for tile in tiles]

    return json.dumps(response, cls=ModelEncoder), 200

@app.route("/v2/events/<id>", methods=['GET'])
def get_event(id):
    """Get a single event by ID"""
    from models.new_events import Team, Tile, TeamMember
    from models.models import Users

    event = CRUDService.get_by_id(Event, id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    # Get related teams and tiles
    teams = Team.query.filter_by(event_id=id).order_by(Team.points.desc()).all()
    tiles = Tile.query.filter_by(event_id=id).order_by(Tile.index).all()

    response = event.serialize()

    # Batch fetch all team members for all teams in one query
    team_ids = [team.id for team in teams]
    all_members = TeamMember.query.filter(TeamMember.team_id.in_(team_ids)).all() if team_ids else []

    # Batch fetch all users for those members in one query
    user_ids = list(set(m.user_id for m in all_members))
    all_users = Users.query.filter(Users.id.in_(user_ids)).all() if user_ids else []
    users_by_id = {user.id: user for user in all_users}

    # Group members by team_id
    members_by_team = {}
    for member in all_members:
        if member.team_id not in members_by_team:
            members_by_team[member.team_id] = []
        members_by_team[member.team_id].append(member)

    # Serialize teams with member names
    teams_data = []
    for team in teams:
        team_dict = team.serialize()
        team_members = members_by_team.get(team.id, [])
        team_dict['members'] = [
            users_by_id[m.user_id].runescape_name
            for m in team_members
            if m.user_id in users_by_id
        ]
        teams_data.append(team_dict)

    response['teams'] = teams_data
    response['tiles'] = [tile.serialize() for tile in tiles]

    return json.dumps(response, cls=ModelEncoder), 200


@app.route("/v2/events", methods=['POST'])
def create_event():
    """Create a new event"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    # Validate required fields
    required_fields = ['name', 'start_date', 'end_date']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    event = CRUDService.create(Event, data)
    if not event:
        return jsonify({'error': 'Failed to create event'}), 500

    return json.dumps(event.serialize(), cls=ModelEncoder), 201

@app.route("/v2/events/<id>", methods=['PUT'])
def update_event(id):
    """Update an event"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON received'}), 400

    event = CRUDService.update(Event, id, data)
    if not event:
        return jsonify({'error': 'Event not found or update failed'}), 404

    return json.dumps(event.serialize(), cls=ModelEncoder), 200

@app.route("/v2/events/<id>", methods=['DELETE'])
def delete_event(id):
    """Delete an event"""
    success = CRUDService.delete(Event, id)
    if not success:
        return jsonify({'error': 'Event not found'}), 404

    return jsonify({'message': 'Event deleted successfully'}), 200


@app.route("/guess", methods=['POST'])
def guess_riddle():
    """
    Submit a guess for a daily riddle.
    
    Request JSON:
    {
        "discord_id": "user_discord_id",
        "item_name": "item_name",
        "location": "location"
    }
    
    Response:
    {
        "item_name_matches": bool,
        "location_matches": bool,
        "puzzle_solved": bool,
        "message": "Appropriate message based on matches"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON received"}), 400
        
        # Validate required fields
        required_fields = ['discord_id', 'item_name', 'location']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        discord_id = str(data['discord_id'])
        item_name = data['item_name'].lower().strip()
        location = data['location'].lower().strip()
        
        now = datetime.now(timezone.utc)
        
        # Find the active event using new_events.Event
        active_event = Event.query.filter(
            Event.start_date <= now,
            Event.end_date >= now
        ).first()
        
        if not active_event:
            return jsonify({"error": "No active event"}), 400
        
        # Find user by discord_id
        user = Users.query.filter_by(discord_id=discord_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Find team for this user
        team_member = TeamMember.query.filter_by(user_id=user.id).first()
        if not team_member:
            return jsonify({"error": "User is not part of a team"}), 400
        
        team = team_member.team
        
        # Get all solved riddles for this team from DailyRiddleSolution table
        solved_solutions = DailyRiddleSolution.query.filter_by(team_id=team.id).all()
        solved_riddle_ids = {solution.riddle_id for solution in solved_solutions}
        
        # Get all unsolved riddles in this event with release_timestamp before current time
        if solved_riddle_ids:
            unsolved_riddles = DailyRiddle.query.filter(
                DailyRiddle.event_id == active_event.id,
                DailyRiddle.release_timestamp <= now,
                ~DailyRiddle.id.in_(solved_riddle_ids)
            ).all()
        else:
            unsolved_riddles = DailyRiddle.query.filter(
                DailyRiddle.event_id == active_event.id,
                DailyRiddle.release_timestamp <= now
            ).all()
        
        # Check matches
        item_name_matches = False
        location_matches = False
        puzzle_solved = False
        solved_riddle = None
        
        # Check if item_name matches any unsolved riddle
        for riddle in unsolved_riddles:
            if riddle.item_name.lower().strip() == item_name:
                item_name_matches = True
                # Check if location also matches the same riddle
                if riddle.location.lower().strip() == location:
                    puzzle_solved = True
                    solved_riddle = riddle
                    break
        
        # Check if location matches any unsolved riddle
        if not location_matches:
            for riddle in unsolved_riddles:
                if riddle.location.lower().strip() == location:
                    location_matches = True
                    break
        
        # Determine appropriate message
        if puzzle_solved:
            # Mark the riddle as solved
            solution = DailyRiddleSolution(
                team_id=team.id,
                riddle_id=solved_riddle.id
            )
            db.session.add(solution)
            # Process an action for solving the riddle
            from services.action_processor import ActionProcessor
            ActionProcessor.process_action(
                player_id=user.id,
                action_name=solved_riddle.name,
                action_type="OTHER"
            )

            db.session.commit()
            message = f"Correct! You solved '{solved_riddle.name}'!"
        elif item_name_matches and location_matches:
            message = f"{item_name}: Matches\n{location}: Matches\nBut they don't match the same puzzle."
        elif item_name_matches:
            message = f"{item_name}: Matches\n{location}: Does not match"
        elif location_matches:
            message = f"{item_name}: Does not match\n{location}: Matches"
        else:
            message = f"{item_name}: Does not match\n{location}: Does not match"
        
        return jsonify({
            "item_name_matches": item_name_matches,
            "location_matches": location_matches,
            "puzzle_solved": puzzle_solved,
            "message": message
        }), 200
        
    except Exception as e:
        logging.error(f"Error processing riddle guess: {str(e)}")
        return jsonify({"error": str(e)}), 500
