from app import app, db
from helper.helpers import ModelEncoder
from helper.set_discord_role import add_discord_role, remove_discord_roles
from flask import request
from sqlalchemy import or_
from models.models import Users, Splits, ClanPointsLog
from models.models import ClanApplications, RankApplications, TierApplications, DiaryApplications, TimeSplitApplications
from models.models import EventTeamMemberMappings, EventTeams
import json
import logging
from datetime import datetime, timezone
from helper.clan_points_helper import increment_clan_points, PointTag

@app.route("/users", methods=['GET'])
def get_users():
    users = Users.query.all()
    data = []
    for row in users:
        if row.is_active:
            data.append(row.serialize())
    return json.dumps(data, cls=ModelEncoder)

@app.route("/users", methods=['POST'])
def create_user():
    data = Users(**request.get_json())
    if data is None:
        return "No JSON received", 400
    user = Users.query.filter_by(discord_id=data.discord_id).first()
    if user is not None and user.is_active:
        return "Id already exists", 400
    
    if user is not None and not user.is_active:
        user.runescape_name = data.runescape_name
        user.previous_names = data.previous_names
        user.is_member = data.is_member if data.is_member is not None else False
        user.rank = data.rank
        user.rank_points = data.rank_points
        user.progression_data = data.progression_data
        user.achievements = data.achievements
        user.join_date = data.join_date
        user.timestamp = datetime.now(timezone.utc)
        user.is_active = True
        user.diary_points = data.diary_points
        user.event_points = data.event_points
        user.time_points = data.time_points
    else:
        db.session.add(data)
    db.session.commit()
    return json.dumps(data.serialize(), cls=ModelEncoder)

@app.route("/users/<id>", methods=['GET'])
def get_user_profile(id):
    user = Users.query.filter(
        Users.is_active == True,
        or_(Users.discord_id == id, Users.runescape_name.ilike(id))
    ).first()

    if user is None:
        return "Could not find User", 404

    return json.dumps(user.serialize(), cls=ModelEncoder)

@app.route("/users/<id>", methods=['PUT'])
def update_user_profile(id):
    data = request.get_json()
    if data is None:
        return "No JSON received", 400
    user = Users.query.filter_by(discord_id=id).first()
    if user is None or not user.is_active:
        return "Could not find User", 404
    
    for key, value in data.items():
        if hasattr(user, key):
            logging.info(f"Updating {key} to {value}")
            setattr(user, key, value)
        else:
            logging.info(f"Key {key} not found in user model")
    
    db.session.commit()
    return json.dumps(user.serialize(), cls=ModelEncoder)

@app.route("/users/<id>", methods=['DELETE'])
def delete_user(id):
    user = Users.query.filter_by(discord_id=id).first()
    if user is None or not user.is_active:
        return "Could not find User", 404
    
    # Don't actually delete the user, just set them to inactive
    user.is_active = False

    # Find all pending applications for this user and delete them
    applications = ClanApplications.query.filter_by(user_id=id).all()
    for application in applications:
        db.session.delete(application)

    applications = RankApplications.query.filter_by(user_id=id).all()
    for application in applications:
        db.session.delete(application)

    applications = TierApplications.query.filter_by(user_id=id).all()
    for application in applications:
        db.session.delete(application)

    applications = DiaryApplications.query.filter_by(user_id=id).all()
    for application in applications:
        db.session.delete(application)

    applications = TimeSplitApplications.query.filter_by(user_id=id).all()
    for application in applications:
        db.session.delete(application)

    db.session.commit()
    return json.dumps("User deleted successfully", cls=ModelEncoder), 200

@app.route("/users/<id>/rename", methods=['PUT'])
def rename_user(id):
    data = Users(**request.get_json())
    if data is None:
        return "No JSON received", 400
    # Ensure the given name is not taken by another user
    existing_user = Users.query.filter_by(runescape_name=data.runescape_name).first()
    if existing_user and existing_user.discord_id != id:
        return "Runescape name already taken", 400
    user = Users.query.filter_by(discord_id=id).first()
    if user is None or not user.is_active:
        return "Could not find User", 404

    # Check if the name is in use by another user
    existing_user = Users.query.filter_by(runescape_name=data.runescape_name).first()
    if existing_user is not None and existing_user.discord_id != id:
        return "Name is already in use", 400

    if not user.previous_names:
        user.previous_names = []
    else:
        # Remove blank entries from previous names
        user.previous_names = [name for name in user.previous_names if name]

    user.previous_names.append(user.runescape_name)
    user.previous_names = list(set(user.previous_names))  # Remove duplicates
    user.runescape_name = data.runescape_name
    
    # Remove new name from previous names if it exists
    if user.runescape_name in user.previous_names:
        user.previous_names.remove(user.runescape_name)

    db.session.commit()
    return json.dumps(user.serialize(), cls=ModelEncoder)

@app.route("/users/<id>/splits", methods=['GET'])
def get_user_splits(id):
    user = Users.query.filter_by(discord_id=id).first()
    if user is None or not user.is_active:
        return "Could not find User", 404
    
    begin_date = request.args.get('begin_date')
    end_date = request.args.get('end_date')
    splits_query = Splits.query.filter_by(user_id=id)

    if begin_date:
        try:
            begin_date = datetime.strptime(begin_date, "%Y-%m-%d")
            splits_query = splits_query.filter(Splits.timestamp >= begin_date)
        except ValueError:
            return "Invalid begin_date format. Use YYYY-MM-DD.", 400
        
    if end_date:
        try:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
            splits_query = splits_query.filter(Splits.timestamp <= end_date)
        except ValueError:
            return "Invalid end_date format. Use YYYY-MM-DD.", 400

    data = []
    splits = splits_query.all()
    for row in splits:
        data.append(row.serialize())
    return json.dumps(data, cls=ModelEncoder)

@app.route("/users/<id>/splits/total", methods=['GET'])
def get_user_total_splits(id):
    user = Users.query.filter_by(discord_id=id).first()
    if user is None or not user.is_active:
        return "Could not find User", 404
    
    begin_date = request.args.get('begin_date')
    end_date = request.args.get('end_date')
    splits_query = Splits.query.filter_by(user_id=id)

    if begin_date:
        try:
            begin_date = datetime.strptime(begin_date, "%Y-%m-%d")
            splits_query = splits_query.filter(Splits.timestamp >= begin_date)
        except ValueError:
            return "Invalid begin_date format. Use YYYY-MM-DD.", 400
        
    if end_date:
        try:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
            splits_query = splits_query.filter(Splits.timestamp <= end_date)
        except ValueError:
            return "Invalid end_date format. Use YYYY-MM-DD.", 400
    data = 0
    splits = splits_query.all()
    for row in splits:
        data += row.split_contribution
    return json.dumps(data, cls=ModelEncoder)

@app.route("/users/<id>/diary/applications", methods=['GET'])
def get_user_diary_applications(id):
    user = Users.query.filter_by(discord_id=id).first()
    if user is None or not user.is_active:
        return "Could not find User", 404
    
    # Separate Pending and Accepted/Rejected applications
    pending_applications = DiaryApplications.query.filter_by(user_id=id, status="Pending").order_by(DiaryApplications.timestamp.desc()).all()
    other_applications = DiaryApplications.query.filter_by(user_id=id).filter(DiaryApplications.status != "Pending").order_by(DiaryApplications.verdict_timestamp.desc()).all()
    
    # Combine the results
    applications = pending_applications + other_applications
    
    data = []
    for row in applications:
        data.append(row.serialize())
    return json.dumps(data, cls=ModelEncoder)

@app.route("/users/<id>/pointlog", methods=['GET'])
def get_user_point_log(id):
    data = []
    rows = ClanPointsLog.query.filter_by(user_id=id).order_by(ClanPointsLog.timestamp.desc()).all()
    for row in rows:
        data.append(row.serialize())
    return data

@app.route("/users/<id>/remove_from_clan", methods=['PUT'])
def remove_user_from_clan(id):
    user = Users.query.filter_by(discord_id=id).first()
    if user is None:
        user = Users.query.filter(Users.runescape_name.ilike(id)).first()
        if user is None:
            return "Could not find User", 404
    
    if not user.is_member:
        return "User is not a member of the clan", 400
    
    # Remove the user from the clan
    user.is_member = False
    user.rank = "Guest"
    add_discord_role(user, "Guest")
    remove_discord_roles(user, ["Member", user.rank])
    time_points = user.time_points
    increment_clan_points(
        user_id=user.discord_id,
        points=-time_points,
        tag=PointTag.TIME,
        message="Removed from clan"
    )

    user.time_points = 0
    user.timestamp = datetime.now(timezone.utc)
    db.session.commit()
    
    return json.dumps(user.serialize(), cls=ModelEncoder)

@app.route("/users/<id>/add_alt", methods=['POST'])
def add_user_alt(id):
    data = request.get_json()
    if data is None:
        return "No JSON received", 400
    
    user: Users = Users.query.filter_by(discord_id=id).first()
    if user is None:
        user: Users = Users.query.filter(Users.runescape_name.ilike(id)).first()
        if user is None:
            return "Could not find User", 404
        
    if not user.is_active:
        return "User is not active", 404
    
    altName = data.get("rsn", None)
    if altName is None:
        return "No RSN provided", 400
    
    if altName in user.alt_names:
        return "Alt already added", 400
    
    existing_user = Users.query.filter(Users.runescape_name.ilike(altName)).first()
    if existing_user and existing_user.discord_id != id:
        return "Runescape name already taken", 400
    
    user.alt_names = user.alt_names + [altName]

    # Get get list of unique team IDs for the user id
    team_ids = db.session.query(EventTeamMemberMappings.team_id).filter_by(discord_id=id).distinct().all()
    team_ids = [team_id[0] for team_id in team_ids]
    for team_id in team_ids:
        # Get the event id from the team id
        event_row = db.session.query(EventTeams.event_id).filter_by(id=team_id).first()
        if event_row:
            # Extract the UUID from the Row object
            event_id = event_row[0]
            # Add the alt to the event team member mapping
            new_mapping = EventTeamMemberMappings(
                event_id=event_id,
                team_id=team_id,
                username=altName,
                discord_id=id,
            )
            db.session.add(new_mapping)

    db.session.commit()
    
    return json.dumps(user.serialize(), cls=ModelEncoder)

@app.route("/users/<id>/remove_alt", methods=['DELETE'])
def remove_user_alt(id):
    data = request.get_json()
    if data is None:
        return "No JSON received", 400
    
    user: Users = Users.query.filter_by(discord_id=id).first()
    if user is None:
        user: Users = Users.query.filter(Users.runescape_name.ilike(id)).first()
        if user is None:
            return "Could not find User", 404
        
    if not user.is_active:
        return "User is not active", 404
    
    altName = data.get("rsn", None)
    if altName is None:
        return "No RSN provided", 400
    
    #check if alt name exists
    if altName not in user.alt_names:
        return "Alt not found", 400
    
    user.alt_names = [name for name in user.alt_names if name != altName]
    # Remove the alt from any event team member mappings
    EventTeamMemberMappings.query.filter_by(username=altName).delete()

    db.session.commit()
    
    return json.dumps(user.serialize(), cls=ModelEncoder)

@app.route("/users/<id>/accounts", methods=['GET'])
def get_user_accounts(id):
    user = Users.query.filter_by(discord_id=id).first()
    if user is None:
        user = Users.query.filter(Users.runescape_name.ilike(id)).first()
        if user is None:
            return "Could not find User", 404
    
    if not user.is_active:
        return "Could not find User", 404
    
    data = [user.runescape_name]
    if not user.alt_names:
        return json.dumps(data, cls=ModelEncoder)
    for row in user.alt_names:
        data.append(row)
    return json.dumps(data, cls=ModelEncoder)
