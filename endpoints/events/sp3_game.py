from app import app, db
from flask import request, jsonify
from models.models import Events, EventTeams, EventTeamMemberMappings, EventTriggers, EventTasks, EventChallenges
from models.stability_party_3 import SP3Regions, SP3EventTiles, SP3EventTileChallengeMapping
from event_handlers.stability_party.stability_party_handler import SaveData, is_shop_tile, is_star_tile, is_dock_tile
import logging
import json
from datetime import datetime, timezone
from helper.helpers import ModelEncoder

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


def get_tile_name(tile_id):
    tile = SP3EventTiles.query.filter_by(id=tile_id).first()
    return tile.name if tile else "Unknown Tile"

def get_region_name(region_id):
    region = SP3Regions.query.filter_by(id=region_id).first()
    return region.name if region else "Unknown Region"

def get_tile_description(tile_id):
    tile = SP3EventTiles.query.filter_by(id=tile_id).first()
    return tile.description if tile else "No description available"

def get_challenge_progress_string(challenge_id, tile_progress):
    challenge = EventChallenges.query.filter_by(id=challenge_id).first()
    if not challenge:
        return "Unknown challenge"

    task_strings = []

    tasks = challenge.tasks
    for task_id in tasks:
        task = EventTasks.query.filter_by(id=task_id).first()
        if task:
            triggers = task.triggers
            trigger_list = []
            for trigger_id in triggers:
                trigger = EventTriggers.query.filter_by(id=trigger_id).first()
                if trigger.type == "DROP":
                    trigger_list.append(f"{trigger.trigger}{' from ' + trigger.source if trigger.source else ''}")
                elif trigger.type == "KC":
                    trigger_list.append(f"{trigger.trigger} KC")
            triggers_message = " OR ".join(trigger_list)
        
            if str(challenge_id) in tile_progress:
                progress = tile_progress[str(challenge_id)]
                if task_id in progress:
                    task_progress = progress[task_id]
                    task_strings.append(f"{task_progress}/{task.quantity} {triggers_message}")
                    continue
            
            task_strings.append(f"0/{task.quantity} {triggers_message}")

    return task_strings

def get_team_tile_challenges(save):
    if save.currentChallenges:
        return save.currentChallenges
    
    if save.currentTile:
        challenges = SP3EventTileChallengeMapping.query.filter_by(
            tile_id=save.currentTile,
            type="TILE"
        ).all()

        return [challenge.challenge_id for challenge in challenges]
    
    return []

def get_team_regional_challenges(save):
    region = SP3Regions.query.filter_by(id=save.islandId).first()
    if not region:
        return []
    
    return region.challenges if region.challenges else []

@app.route("/events/<event_id>/users/<discord_id>/team", methods=['GET'])
def get_user_team(event_id, discord_id):
    """Get the team associated with a Discord ID"""
    try:
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team_mapping = EventTeamMemberMappings.query.filter_by(event_id=event_id, discord_id=discord_id).first()
        if not team_mapping:
            return jsonify({"error": "No team found for this Discord ID"}), 404
        
        # Get the team details
        team = EventTeams.query.filter_by(id=team_mapping.team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found for this event"}), 404
        
        return json.dumps(team.serialize(), cls=ModelEncoder), 200
    except Exception as e:
        logging.error(f"Error getting user team: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/teams/<team_id>/stats", methods=['GET'])
def get_team_stats(event_id, team_id):
    """Get the current stats for a team"""
    try:
        logging.info(f"Getting stats for team {team_id} in event {event_id}")
        
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            logging.warning(f"Event {event_id} not found or not a Stability Party event")
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team: EventTeams = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if team is None:
            logging.warning(f"Team {team_id} not found or does not belong to event {event_id}")
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        logging.debug(f"Found team {team.name} (ID: {team_id})")
        
        # Get team members
        members: EventTeamMemberMappings = EventTeamMemberMappings.query.filter_by(event_id=event_id, team_id=team_id).all()
        logging.debug(f"Found {len(members)} team members")
        member_names = [member.username for member in members]
        
        # Get team stats
        save = SaveData.from_dict(team.data)
        
        # Find the current tile information
        current_tile = SP3EventTiles.query.filter_by(
            id=save.currentTile,
            event_id=event_id
        ).first()
        
        tile_info = None
        if current_tile:
            logging.debug(f"Current tile: {current_tile.name}")
            tile_info = {
                "id": str(current_tile.id),
                "name": current_tile.name,
                "description": current_tile.description
            }
        else:
            logging.warning(f"Current tile information not found for tile {save.currentTile}")
        
        # Find the current island/region information
        current_region = SP3Regions.query.filter_by(
            event_id=event_id,
            id=save.islandId
        ).first()
        
        region_info = None
        if current_region:
            logging.debug(f"Current region: {current_region.name}")
            region_info = {
                "id": str(current_region.id),
                "name": current_region.name,
                "description": current_region.description
            }
        else:
            logging.warning(f"Current region information not found for island ID {save.islandId}")
        
        star_locations: list[dict] = []
        star_tiles = event.data["star_tiles"]
        for star_tile in star_tiles:
            tile = SP3EventTiles.query.filter_by(
                event_id=event_id,
                id=star_tile
            ).first()
            if tile:
                star_locations.append({
                    "tile": str(tile.id),
                    "name": tile.name,
                    "description": tile.description,
                    "region": get_region_name(tile.region_id)
                })

        stats = {
            "team_name": team.name,
            "captain": str(team.captain),
            "members": member_names,
            "stars": save.stars,
            "coins": save.coins,
            "current_location": {
                "tile": save.currentTile,
                "tile_info": tile_info,
                "region": region_info
            },
            "tile_completed": save.isTileCompleted,
            "equipment": save.equipment.to_dict(),
            "buffs": save.buffs,
            "debuffs": save.debuffs,
            "items": save.itemList,
            "is_rolling": save.isRolling,
            "event_star_locations": star_locations
        }
        
        logging.info(f"Successfully retrieved stats for team {team.name} (ID: {team_id})")
        return jsonify(stats), 200
    except Exception as e:
        logging.error(f"Error getting team stats: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/teams/<team_id>/tile-progress", methods=['GET'])
def get_team_tile_progress(event_id, team_id):
    """Get the current tile progress for a team"""
    try:
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Get team data
        save = SaveData.from_dict(team.data)

        tile_challenges = get_team_tile_challenges(save)
        region_challenges = get_team_regional_challenges(save)

        tile_progress = []
        for challenge in tile_challenges:
            progress_strings = get_challenge_progress_string(challenge, save.tileProgress)
            for progress_string in progress_strings:
                tile_progress.append(progress_string)

        region_progress = []
        for challenge in region_challenges:
            progress_strings = get_challenge_progress_string(challenge, save.tileProgress)
            for progress_string in progress_strings:
                region_progress.append(progress_string)

        response = {
            "team_name": team.name,
            "current_tile": get_tile_name(save.currentTile),
            "current_region": get_region_name(save.islandId),
            "tile_description": get_tile_description(save.currentTile),
            "tile_progress": tile_progress,
            "region_progress": region_progress,
            "is_tile_completed": save.isTileCompleted,
            "is_rolling": save.isRolling,
        }
        
        return jsonify(response), 200
    except Exception as e:
        logging.error(f"Error getting tile progress: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@app.route("/events/<event_id>/teams/<team_id>/total-progress", methods=['GET'])
def get_team_total_progress(event_id, team_id):
    """Get the total progress of a team in the event"""
    try:
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Check if team exists and belongs to this event
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            return jsonify({"error": "Team not found or does not belong to this event"}), 404
        
        # Get team data
        save = SaveData.from_dict(team.data)

        def get_challenge_progress_string(challenge_id, tile_progress):
            challenge = EventChallenges.query.filter_by(id=challenge_id).first()
            if not challenge:
                return "Unknown challenge"

            task_strings = []

            tasks = challenge.tasks
            for task_id in tasks:
                task = EventTasks.query.filter_by(id=task_id).first()
                if task:
                    triggers = task.triggers
                    trigger_list = []
                    for trigger_id in triggers:
                        trigger = EventTriggers.query.filter_by(id=trigger_id).first()
                        if trigger.type == "DROP":
                            trigger_list.append(f"{trigger.trigger}{' from ' + trigger.source if trigger.source else ''}")
                        elif trigger.type == "KC":
                            trigger_list.append(f"{trigger.trigger} KC")
                    triggers_message = " OR ".join(trigger_list)
                
                    if str(challenge_id) in tile_progress:
                        progress = tile_progress[str(challenge_id)]
                        if task_id in progress:
                            task_progress = progress[task_id]
                            task_strings.append(f"{task_progress}/{task.quantity} {triggers_message}")
                            continue
                    
                    task_strings.append(f"0/{task.quantity} {triggers_message}")

            return task_strings

        # Get all tile progress
        for challenge_id, tasks in save.tileProgress.items():
            for task_id, task_progress in tasks.items():
                if task_progress >= 1:
                    save.isTileCompleted = True
                    break
        
        # Calculate total progress
        total_progress = {
            "stars": save.stars,
            "coins": save.coins,
            "completed_tiles": save.isTileCompleted,
            "is_rolling": save.isRolling,
            "current_tile": str(save.currentTile),
            "current_region": str(save.islandId)
        }
        
        return jsonify(total_progress), 200
    except Exception as e:
        logging.error(f"Error getting total progress: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/progress", methods=['GET'])
def get_event_progress(event_id):
    """Get the overall progress of the event including team standings"""
    try:
        # Check if event exists and is a SP3 event
        event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
        if not event:
            return jsonify({"error": "Event not found or not a Stability Party event"}), 404
        
        # Calculate time until event end
        now = datetime.now(timezone.utc)
        time_remaining = None
        if event.end_time:
            end_time = event.end_time.replace(tzinfo=timezone.utc)
            time_delta = end_time - now
            time_remaining = max(0, time_delta.total_seconds())
        
        # Get all teams for this event
        teams = EventTeams.query.filter_by(event_id=event_id).all()
        
        # Prepare team standings
        standings = []
        for team in teams:
            save = SaveData.from_dict(team.data)
            
            # Get current tile information
            current_tile = SP3EventTiles.query.filter_by(
                event_id=event_id, 
                tile_number=save.currentTile
            ).first()
            
            # Get current region information  
            current_region = SP3Regions.query.filter_by(
                event_id=event_id,
                id=save.islandId
            ).first()
            
            region_name = current_region.name if current_region else "Unknown"
            
            standings.append({
                "team_id": str(team.id),
                "team_name": team.name,
                "stars": save.stars,
                "coins": save.coins,
                "current_tile": save.currentTile,
                "current_region": region_name,
                "tile_completed": save.isTileCompleted
            })
        
        # Sort by stars (descending) and then by coins (descending)
        standings.sort(key=lambda x: (x["stars"], x["coins"]), reverse=True)
        
        # Add ranking to each team
        for i, team in enumerate(standings):
            team["rank"] = i + 1
        
        # Get event regions/islands
        regions = SP3Regions.query.filter_by(event_id=event_id).all()
        region_info = []
        for region in regions:
            region_info.append({
                "id": str(region.id),
                "name": region.name,
                "description": region.description
            })
        
        response = {
            "event_id": event_id,
            "event_name": event.name,
            "event_description": event.description,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "time_remaining_seconds": time_remaining,
            "regions": region_info,
            "team_standings": standings,
            "total_teams": len(teams)
        }
        
        return jsonify(response), 200
    except Exception as e:
        logging.error(f"Error getting event progress: {str(e)}")
        return jsonify({"error": str(e)}), 500

class RollProgressionPayload():
    eventId: str
    teamId: str

    startingTileId: str
    currentTileId: str

    rollDistanceTotal: int
    rollDistanceRemaining: int

    data: dict

@app.route("/events/<event_id>/teams/<team_id>/roll", methods=['POST'])
def roll_dice(event_id, team_id):
    """Start a new dice roll or continue an existing roll progression"""
    try:
        # Get data from request (optional)
        data = None
        try:
            if request.is_json and request.data:
                data = request.get_json(force=False, silent=True)
        except Exception as e:
            logging.warning(f"Error parsing request data: {str(e)}")
        
        # Process the roll using the progression helper
        from event_handlers.stability_party.stability_party_handler import roll_dice_progression
        response, status_code = roll_dice_progression(event_id, team_id, data)
        
        return jsonify(response), status_code
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error rolling dice: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/teams/<team_id>/roll/continue", methods=['POST'])
def continue_roll(event_id, team_id):
    """Continue a roll in progress"""
    try:
        # Get data from request (optional)
        data = None
        try:
            if request.is_json and request.data:
                data = request.get_json(force=False, silent=True)
        except Exception as e:
            logging.warning(f"Error parsing request data: {str(e)}")
        
        # Process the roll using the progression helper
        from event_handlers.stability_party.stability_party_handler import roll_dice_progression, RollState
        response, status_code = roll_dice_progression(
            event_id, 
            team_id, 
            data, 
            action_type=RollState.ACTION_TYPES["CONTINUE"]
        )
        
        return jsonify(response), status_code
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error continuing roll: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/teams/<team_id>/roll/shop", methods=['POST'])
def shop_action(event_id, team_id):
    """Handle shop interactions during a roll"""
    try:
        # Get data from request
        data = None
        try:
            if request.is_json and request.data:
                data = request.get_json(force=False, silent=True)
        except Exception as e:
            logging.warning(f"Error parsing request data: {str(e)}")
        
        # Process the shop action using the progression helper
        from event_handlers.stability_party.stability_party_handler import roll_dice_progression, RollState
        response, status_code = roll_dice_progression(
            event_id, 
            team_id, 
            data, 
            action_type=RollState.ACTION_TYPES["SHOP"]
        )
        
        return jsonify(response), status_code
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error processing shop action: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/teams/<team_id>/roll/star", methods=['POST'])
def star_action(event_id, team_id):
    """Handle star purchase during a roll"""
    try:
        # Get data from request
        data = None
        try:
            if request.is_json and request.data:
                data = request.get_json(force=False, silent=True)
        except Exception as e:
            logging.warning(f"Error parsing request data: {str(e)}")
        
        # Process the star action using the progression helper
        from event_handlers.stability_party.stability_party_handler import roll_dice_progression, RollState
        response, status_code = roll_dice_progression(
            event_id, 
            team_id, 
            data, 
            action_type=RollState.ACTION_TYPES["STAR"]
        )
        
        return jsonify(response), status_code
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error processing star action: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/teams/<team_id>/roll/dock", methods=['POST'])
def dock_action(event_id, team_id):
    """Handle dock/charter ship interactions during a roll"""
    try:
        # Get data from request
        data = None
        try:
            if request.is_json and request.data:
                data = request.get_json(force=False, silent=True)
        except Exception as e:
            logging.warning(f"Error parsing request data: {str(e)}")
        
        # Process the dock action using the progression helper
        from event_handlers.stability_party.stability_party_handler import roll_dice_progression, RollState
        response, status_code = roll_dice_progression(
            event_id, 
            team_id, 
            data, 
            action_type=RollState.ACTION_TYPES["DOCK"]
        )
        
        return jsonify(response), status_code
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error processing dock action: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/teams/<team_id>/roll/crossroad", methods=['POST'])
def crossroad_action(event_id, team_id):
    """Handle path selection at a crossroad during a roll"""
    try:
        # Get data from request
        data = None
        try:
            if request.is_json and request.data:
                data = request.get_json(force=False, silent=True)
        except Exception as e:
            logging.warning(f"Error parsing request data: {str(e)}")
        
        # Process the crossroad action using the progression helper
        from event_handlers.stability_party.stability_party_handler import roll_dice_progression, RollState
        response, status_code = roll_dice_progression(
            event_id, 
            team_id, 
            data, 
            action_type=RollState.ACTION_TYPES["CROSSROAD"]
        )
        
        return jsonify(response), status_code
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error processing crossroad action: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/teams/<team_id>/roll/first_island", methods=['POST'])
def first_island_action(event_id, team_id):
    """Handle first island selection during a roll"""
    try:
        # Get data from request
        data = None
        try:
            if request.is_json and request.data:
                data = request.get_json(force=False, silent=True)
        except Exception as e:
            logging.warning(f"Error parsing request data: {str(e)}")
        
        # Process the first island action using the progression helper
        from event_handlers.stability_party.stability_party_handler import roll_dice_progression, RollState
        response, status_code = roll_dice_progression(
            event_id, 
            team_id, 
            data, 
            action_type=RollState.ACTION_TYPES["ISLAND_SELECTION"]
        )
        
        return jsonify(response), status_code
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error processing first island action: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/events/<event_id>/teams/<team_id>/available-actions", methods=['GET'])
def get_available_actions(event_id, team_id):
    """Get available actions for a team based on their current position"""
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
        
        # Get the current tile information
        current_tile = SP3EventTiles.query.filter_by(
            event_id=event_id, 
            tile_number=save.currentTile
        ).first()
        
        if not current_tile:
            return jsonify({"error": "Current tile information not found"}), 404
        
        # Determine available actions
        available_actions = []
        
        # If the tile is completed, they can roll
        if save.isTileCompleted and not save.isRolling:
            available_actions.append({
                "action": "roll",
                "description": "Roll dice to move forward"
            })
        
        # If they are in the middle of rolling and on a special tile
        if save.isRolling:
            if is_shop_tile(current_tile.id):
                available_actions.append({
                    "action": "buy_item",
                    "description": "Buy an item from the shop"
                })
            elif is_star_tile(current_tile.id):
                available_actions.append({
                    "action": "buy_star",
                    "description": "Buy a star" 
                })
            elif is_dock_tile(current_tile.id):
                # Get available destinations
                regions = SP3Regions.query.filter_by(event_id=event_id).all()
                destinations = []
                for region in regions:
                    if region.id != save.islandId:  # Don't include current island
                        destinations.append({
                            "id": str(region.id),
                            "name": region.name
                        })
                
                if destinations:
                    available_actions.append({
                        "action": "charter_ship",
                        "description": "Charter a ship to another island",
                        "destinations": destinations
                    })
        
        # Return the available actions
        response = {
            "current_tile": {
                "number": save.currentTile,
                "name": current_tile.name,
                "description": current_tile.description
            },
            "is_completed": save.isTileCompleted,
            "is_rolling": save.isRolling,
            "available_actions": available_actions
        }
        
        return jsonify(response), 200
    except Exception as e:
        logging.error(f"Error getting available actions: {str(e)}")
        return jsonify({"error": str(e)}), 500