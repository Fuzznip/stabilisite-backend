from app import app, db
from flask import request, jsonify
from models.models import Events, EventTeams, EventTeamMemberMappings, Users
from models.stability_party_3 import SP3Regions, SP3EventTiles, SP3EventTileChallengeMapping
from event_handlers.stability_party.stability_party_handler import SaveData, save_team_data
from sqlalchemy.orm.attributes import flag_modified
from helper.discord_helper import create_discord_role, create_discord_text_channel, create_discord_voice_channel
from helper.set_discord_role import add_discord_role
import uuid
import logging
import json
import random
import os
from datetime import datetime, timezone
from helper.helpers import ModelEncoder


@app.route("/events/<event_id>/moderation/teams", methods=['POST'])
def create_team(event_id):
    """Create a new team for the given event"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if "name" not in data:
            return jsonify({"error": "Missing required field: name"}), 400
        
        # Discord ID is required to identify the captain
        if "discord_id" not in data:
            return jsonify({"error": "Missing required field: discord_id"}), 400
        
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Look up user by Discord ID
        user = Users.query.filter_by(discord_id=data["discord_id"]).first()
        
        # If user doesn't exist, create a guest profile
        if not user:
            logging.info(f"Creating guest user profile for captain with Discord ID {data['discord_id']}")
            username = data.get("username", f"Captain-{data['discord_id']}")  # Use provided username or generate one
            
            user = Users(
                id=uuid.uuid4(),
                discord_id=data["discord_id"],
                runescape_name=username,
                is_member=False,
                rank="Guest",
                is_active=True,
                join_date=datetime.now(timezone.utc),
                timestamp=datetime.now(timezone.utc)
            )
            db.session.add(user)
            db.session.commit()
            logging.info(f"Created guest user for captain: {user.id}")
        
        # Create Discord role and channels
        role_id = create_discord_role(data["name"])
        if not role_id:
            return jsonify({"error": "Failed to create Discord role for team"}), 500
        
        # Create text and voice channels
        text_channel_name = f"{data['name'].lower().replace(' ', '-')}" 
        voice_channel_name = data['name']
        
        text_channel_id = create_discord_text_channel(channel_name=text_channel_name, role_id_list=[role_id])
        if not text_channel_id:
            return jsonify({"error": "Failed to create Discord text channel for team"}), 500
        
        voice_channel_id = create_discord_voice_channel(voice_channel_name, role_id)
        if not voice_channel_id:
            return jsonify({"error": "Failed to create Discord voice channel for team"}), 500
        
        # Create new team with the captain's user ID
        team = EventTeams(
            event_id=event_id,
            name=data["name"],
            captain=user.id,  # Use the user's UUID (not the discord_id)
            image=data.get("image", None),
            data={}
        )
        
        # Initialize SaveData for the team
        save_data = SaveData()
        save_data.previousTile = None
        save_data.currentTile = None
        save_data.stars = 0
        save_data.coins = 0
        save_data.islandId = None
        save_data.itemList = []
        save_data.equipment = None
        save_data.dice = []
        save_data.modifier = 0
        save_data.isTileCompleted = True
        save_data.isRolling = False
        save_data.buffs = []
        save_data.debuffs = []
        save_data.textChannelId = text_channel_id
        save_data.voiceChannelId = voice_channel_id
        save_data.tileProgress = {}
        
        # Save the team with initialized data
        team.data = save_data.to_dict()
        db.session.add(team)
        db.session.commit()
        
        # Add the captain as the first team member
        member = EventTeamMemberMappings(
            event_id=event_id,
            team_id=team.id,
            username=user.runescape_name,
            discord_id=data["discord_id"]
        )
        db.session.add(member)
        db.session.commit()
        
        return jsonify({
            "message": "Team created successfully",
            "team_id": str(team.id),
            "captain_id": str(user.id),
            "captain_discord_id": data["discord_id"],
            "captain_username": user.runescape_name,
            "discord": {
                "role_id": role_id,
                "text_channel_id": text_channel_id,
                "voice_channel_id": voice_channel_id
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error creating team: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/events/<event_id>/moderation/teams/<team_id>/rename", methods=['POST'])
def rename_team(event_id, team_id):
    """Rename an existing team"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if "name" not in data:
            return jsonify({"error": "Missing required field: name"}), 400
        
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Update team name
        team.name = data["name"]
        db.session.commit()
        
        return jsonify({"message": "Team renamed successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error renaming team: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/events/<event_id>/moderation/teams/<team_id>/members", methods=['GET'])
def get_team_members(event_id, team_id):
    """Get members of a team"""
    try:
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Get members of the team
        members = EventTeamMemberMappings.query.filter_by(team_id=team_id).all()
        
        # Filter members to only include those that match entries in the Users table
        valid_members = []
        for member in members:
            # Check if there's a matching user in the Users table
            user = Users.query.filter_by(discord_id=member.discord_id).first()
            if user and (user.runescape_name == member.username):
                valid_members.append({
                    "member_id": str(member.id),
                    "username": member.username,
                    "discord_id": member.discord_id
                })
        
        return json.dumps(valid_members, cls=ModelEncoder), 200
    except Exception as e:
        logging.error(f"Error getting team members: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/moderation/teams/<team_id>/members", methods=['POST'])
def add_player_to_team(event_id, team_id):
    """Add a player to a team"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if "username" not in data:
            return jsonify({"error": "Missing required field: username"}), 400
            
        # Discord ID is now required
        if "discord_id" not in data:
            return jsonify({"error": "Missing required field: discord_id"}), 400
        
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Check if player is already on a team for this event by discord ID
        existing_member_by_discord = EventTeamMemberMappings.query.filter_by(
            event_id=event_id, discord_id=data["discord_id"]).first()
        if existing_member_by_discord:
            return jsonify({"error": "Player is already on a team for this event (by Discord ID)"}), 400
            
        # Check if player is already on a team for this event by username
        existing_member_by_username = EventTeamMemberMappings.query.filter_by(
            event_id=event_id, username=data["username"]).first()
        if existing_member_by_username:
            return jsonify({"error": "Player is already on a team for this event (by username)"}), 400
        
        # Look up user by Discord ID
        user = Users.query.filter_by(discord_id=data["discord_id"]).first()
        
        # If user doesn't exist, create a guest profile
        if not user:
            logging.info(f"Creating guest user profile for Discord ID {data['discord_id']} with username {data['username']}")
            user = Users(
                id=uuid.uuid4(),
                discord_id=data["discord_id"],
                runescape_name=data["username"],
                is_member=False,
                rank="Guest",
                is_active=True,
                join_date=None,
                timestamp=datetime.now(timezone.utc)
            )
            db.session.add(user)
            db.session.commit()
            logging.info(f"Created guest user: {user.id}")
            
        # Add player to team
        member = EventTeamMemberMappings(
            event_id=event_id,
            team_id=team_id,
            username=user.runescape_name,
            discord_id=data["discord_id"]
        )
        db.session.add(member)

        # Add alts to the team if they exist
        print(f"Adding alt names for user {user.runescape_name}: {user.alt_names}")
        if user.alt_names is None:
            user.alt_names = []
        for alt_username in user.alt_names:
            if alt_username is None or alt_username == "":
                continue

            alt_member = EventTeamMemberMappings(
                event_id=event_id,
                team_id=team_id,
                username=alt_username,
                discord_id=data["discord_id"]
            )
            db.session.add(alt_member)

        db.session.commit()

        # FIXME: Add discord role using the role ID in the future
        add_discord_role(user, team.name)

        return jsonify({
            "message": "Player added to team successfully",
            "member_id": str(member.id),
            "discord_id": data["discord_id"],
            "user_created": user is not None,
            "user_is_guest": not user.is_member if user else True
        }), 201
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error adding player to team: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/moderation/teams/<team_id>/members/<member_id>", methods=['DELETE'])
def remove_player_from_team(event_id, team_id, member_id):
    """Remove a player from a team"""
    try:
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Check if member exists and belongs to the team
        members = EventTeamMemberMappings.query.filter_by(discord_id=member_id).all()
        if not members:
            return jsonify({"error": "Member not found"}), 404
            
        for m in members:
            if str(m.team_id) != team_id or str(m.event_id) != event_id:
                continue
            # Remove player from team
            db.session.delete(m)

        db.session.commit()
        
        return jsonify({"message": "Player removed from team successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error removing player from team: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/moderation/teams/<team_id>/members/<member_id>/usernames", methods=['POST'])
def add_associated_username(event_id, team_id, member_id):
    """Add an associated username to a player"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if "alt_username" not in data:
            return jsonify({"error": "Missing required field: alt_username"}), 400
        
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Check if member exists and belongs to the team
        member = EventTeamMemberMappings.query.filter_by(id=member_id).first()
        if not member or str(member.team_id) != team_id or str(member.event_id) != event_id:
            return jsonify({"error": "Member not found or not part of this team"}), 404
        
        # Add alt username (create a new mapping with the same team_id but different username)
        # Transfer the discord_id from the original member mapping to maintain the relationship
        alt_member = EventTeamMemberMappings(
            event_id=event_id,
            team_id=team_id,
            username=data["alt_username"],
            discord_id=member.discord_id
        )
        db.session.add(alt_member)
        db.session.commit()
        
        return jsonify({
            "message": "Associated username added successfully", 
            "alt_member_id": str(alt_member.id),
            "discord_id": member.discord_id
        }), 201
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error adding associated username: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/moderation/teams/<team_id>/members/<member_id>/usernames", methods=['DELETE'])
def remove_associated_username(event_id, team_id, member_id):
    """Remove an associated username from a player"""
    return remove_player_from_team(event_id, team_id, member_id)

@app.route("/events/<event_id>/moderation/teams/<team_id>/complete-tile", methods=['POST'])
def force_complete_tile(event_id, team_id):
    """Force completion of a tile for a team"""
    try:
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Load team data
        save = SaveData.from_dict(team.data)
        
        # Force complete the current tile
        save.isTileCompleted = True
        save.isRolling = False

        save.currentChallenges = []
        
        # Save the updated team data
        save_team_data(team, save)
        
        return jsonify({"message": "Tile marked as completed successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error completing tile: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/events/<event_id>/moderation/teams/<team_id>/stars", methods=['PUT'])
def set_team_stars(event_id, team_id):
    """Set the amount of stars a team has"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if "stars" not in data:
            return jsonify({"error": "Missing required field: stars"}), 400
        
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Load team data
        save = SaveData.from_dict(team.data)
        
        # Update stars
        save.stars = int(data["stars"])
        
        # Save the updated team data
        save_team_data(team, save)
        
        return jsonify({"message": "Team stars updated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating team stars: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/events/<event_id>/moderation/teams/<team_id>/coins", methods=['PUT'])
def set_team_coins(event_id, team_id):
    """Set the amount of coins a team has"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if "coins" not in data:
            return jsonify({"error": "Missing required field: coins"}), 400
        
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Load team data
        save = SaveData.from_dict(team.data)
        
        # Update coins
        save.coins = int(data["coins"])
        
        # Save the updated team data
        save_team_data(team, save)
        
        return jsonify({"message": "Team coins updated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating team coins: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/moderation/teams/<team_id>/move-to-tile", methods=['PUT'])
def move_team_to_tile(event_id, team_id):
    """Move a team to a specific tile"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if "tile_id" not in data:
            return jsonify({"error": "Missing required field: tile_id"}), 400
        
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Load team data
        save = SaveData.from_dict(team.data)
        
        # Move the team to the specified tile
        save.previousTile = save.currentTile
        save.currentTile = uuid.UUID(data["tile_id"])
        tile: SP3EventTiles = SP3EventTiles.query.filter_by(id=save.currentTile).first()
        region = tile.region_id
        save.islandId = region

        # Set the random challenges if the new tile is a RANDOM tile
        if tile.data["category"] == "RANDOM":
            challenges = SP3EventTileChallengeMapping.query.filter_by(tile_id=tile.id).all()
            save.currentChallenges = [random.choice(challenges).challenge_id]
        else:
            save.currentChallenges = []
        
        # Save the updated team data
        save_team_data(team, save)
        
        tile = SP3EventTiles.query.filter_by(id=save.currentTile).first()

        return jsonify({"message": f"Team moved to tile {tile.name} successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error moving team to tile: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/moderation/teams/<team_id>/undo-roll", methods=['POST'])
def undo_team_roll(event_id, team_id):
    """Undo a team's last turn they rolled for"""
    try:
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Load team data
        save = SaveData.from_dict(team.data)

        # TODO: Undo roll logic
        
        # Save the updated team data
        save_team_data(team, save)
        
        return jsonify({"message": "Team's last roll undone successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error undoing team roll: {str(e)}")
        return jsonify({"error": str(e)}), 500
