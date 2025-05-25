from app import db
from event_handlers.event_handler import EventSubmission, NotificationResponse, NotificationAuthor, NotificationField
from models.models import Events, EventTeams, EventTeamMemberMappings, EventChallenges, EventTasks, EventTriggers
from models.stability_party_3 import SP3Regions, SP3EventTiles, SP3EventTileChallengeMapping
from event_handlers.stability_party.item_system import generate_shop_inventory, get_item_by_id, add_item_to_inventory
from event_handlers.stability_party.item_definitions import get_items_by_rarity
from event_handlers.stability_party.save_data import RollState, SaveData, save_team_data
from event_handlers.stability_party.send_event_notification import send_event_notification
import uuid
import logging
import random
import requests
from datetime import datetime, timezone
from sqlalchemy.orm.attributes import flag_modified  # Add this import

def get_team_challenges(save: SaveData) -> list[SP3EventTileChallengeMapping]:
    challenges: list[SP3EventTileChallengeMapping] = []
    # Ensure save.currentTile is not None before querying
    if save.currentChallenges:
        for challenge_id in save.currentChallenges:
            challenge = SP3EventTileChallengeMapping.query.filter(SP3EventTileChallengeMapping.challenge_id == challenge_id).first()
            if challenge:
                challenges.append(challenge)
    elif save.currentTile:
        teamChallenges = SP3EventTileChallengeMapping.query.filter(SP3EventTileChallengeMapping.tile_id == save.currentTile).all()
        for challenge in teamChallenges:
            challenges.append(challenge)
    return challenges

def is_challenge_completed(challenge: EventChallenges, task: EventTasks, save: SaveData) -> bool:
    challengeId = str(challenge.id)
    taskId = str(task.id)
    
    # Ensure progress structure exists
    if challengeId not in save.tileProgress or taskId not in save.tileProgress[challengeId]:
        logging.warning(f"Progress not found for challenge {challengeId}, task {taskId}. Assuming not met.")
        return False

    match challenge.type:
        case "OR":
            if save.tileProgress[challengeId][taskId] >= task.quantity:
                # For OR, typically you don't decrement progress unless it's a consumable OR challenge.
                # If it's "complete one of these tasks", then once one is done, the challenge is done.
                # If it's "do X of this OR Y of that", then decrementing might make sense if tasks can be repeated for same challenge.
                # For now, assuming simple completion.
                save.tileProgress[challengeId][taskId] -= task.quantity
                return True
        case "AND":
            # Check all tasks for an AND challenge
            all_tasks_completed = True
            for t_id_str in challenge.tasks:
                current_task_obj = EventTasks.query.filter_by(id=t_id_str).first()
                if not current_task_obj:
                    logging.warning(f"Task {t_id_str} not found for AND challenge {challengeId}")
                    return False # Cannot complete if a task definition is missing
                
                if challengeId not in save.tileProgress or \
                   str(current_task_obj.id) not in save.tileProgress[challengeId] or \
                   save.tileProgress[challengeId][str(current_task_obj.id)] < current_task_obj.quantity:
                    all_tasks_completed = False
                    break
            
            if all_tasks_completed:
                # If all tasks are met, then decrement progress for all of them
                # for t_id_str in challenge.tasks:
                #     current_task_obj = EventTasks.query.filter_by(id=t_id_str).first()
                #     if current_task_obj: # Should exist if we got here
                #         save.tileProgress[challengeId][str(current_task_obj.id)] -= current_task_obj.quantity
                # This decrementing logic for AND might need refinement based on game rules
                # (e.g., are tasks "consumed" or just "checked"?)
                # For now, let's assume completion means they are met, not necessarily consumed from progress.
                pass
            return all_tasks_completed
            
        case "CUMULATIVE":
            logging.warning(f"Challenge {challengeId} is cumulative, but completion logic is not implemented")
            return False 
    return False

def create_region_challenge_notification(challenge: EventChallenges, event: Events, team: EventTeams, save: SaveData, submission: EventSubmission) -> NotificationResponse:
    region = SP3Regions.query.filter(SP3Regions.id == save.islandId).first()
    if not region:
        logging.error(f"Region not found for region ID {save.islandId} during notification creation.")
        return None

    # Example rewards - customize as needed
    coins_earned = 50
    # Base dice - a D6 if no dice, otherwise use existing dice
    dice_earned = [6] if not save.dice else save.dice

    save.coins += coins_earned
    # Logic for adding dice: append, replace, or based on rules
    # For now, let's assume it replaces or is the only dice they get from this
    save.dice = dice_earned
    save.isTileCompleted = True
    save.currentChallenges = []

    fields = [
        NotificationField(name="Stars", value=save.stars, inline=True),
        NotificationField(name="Coins", value=save.coins, inline=True),
        NotificationField(name="Island", value=region.name, inline=True),
        NotificationField(name="New Dice", value=f"Earned a {dice_earned[0]} sided die!", inline=True)
    ]

    if submission.type == "LOOT":
        notification_title = f"{submission.rsn}: {f"{submission.quantity}x " if submission.quantity > 1 else ""}{submission.trigger} from {submission.source}"
    elif submission.type == "KC":
        notification_title = f"{submission.rsn}: Killed {submission.trigger}"
    else:
        notification_title = f"{submission.rsn}: {f"{submission.quantity}x " if submission.quantity > 1 else ""}{submission.trigger} from {submission.source}"

    return NotificationResponse(
        threadId=event.thread_id,
        title=notification_title,
        description=f"For completing the Region Challenge on **{region.name}**, {team.name} have earned {coins_earned} coins and a {dice_earned[0]}-sided die!",
        color=0x992D22, # Example color
        author=NotificationAuthor(name=f"{team.name}: {region.name}", icon_url=team.image if team.image else None),
        fields=fields,
    )

def create_tile_challenge_notification(challenge_mapping: SP3EventTileChallengeMapping, event: Events, team: EventTeams, save: SaveData, submission: EventSubmission) -> NotificationResponse:
    tile = SP3EventTiles.query.filter(SP3EventTiles.id == save.currentTile).first()
    if not tile:
        logging.error(f"Tile not found for currentTile ID {save.currentTile} during notification creation.")
        return None
    region = SP3Regions.query.filter(SP3Regions.id == tile.region_id).first()
    if not region:
        logging.error(f"Region not found for region_id {tile.region_id} during notification creation.")
        return None

    # Example rewards - customize as needed
    if region.data.get("isHotspot", False):
        coins_earned = 10
    else:
        coins_earned = max(10 - save.islandLaps * 2, 0)
    # Base dice - a D4 if no dice, otherwise use existing dice
    dice_earned = [4] if not save.dice else save.dice

    save.coins += coins_earned
    # Logic for adding dice: append, replace, or based on rules
    # For now, let's assume it replaces or is the only dice they get from this
    save.dice = dice_earned 
    save.isTileCompleted = True # This specific TILE challenge type completes the tile
    save.currentChallenges = []

    fields = [
        NotificationField(name="Stars", value=save.stars, inline=True),
        NotificationField(name="Coins", value=save.coins, inline=True),
        NotificationField(name="Island", value=region.name, inline=True),
        NotificationField(name="New Dice", value=f"Earned a {dice_earned[0]} sided die!", inline=True)
    ]

    if submission.type == "LOOT":
        notification_title = f"{submission.rsn}: {f"{submission.quantity}x " if submission.quantity > 1 else ""}{submission.trigger} from {submission.source}"
    elif submission.type == "KC":
        notification_title = f"{submission.rsn}: Killed {submission.trigger}"
    else:
        notification_title = f"{submission.rsn}: {f"{submission.quantity}x " if submission.quantity > 1 else ""}{submission.trigger} from {submission.source}"

    return NotificationResponse(
        threadId=event.thread_id,
        title=notification_title,
        description=f"For completing the tile: **{tile.name}**, {team.name} have earned {coins_earned} coins and a {dice_earned[0]}-sided die!",
        color=0x992D22, # Example color
        author=NotificationAuthor(name=f"{team.name}: {tile.name} ({region.name})", icon_url=team.image if team.image else None),
        fields=fields,
    )

def create_coin_challenge_notification(challenge_mapping: SP3EventTileChallengeMapping, event: Events, team: EventTeams, save: SaveData, submission: EventSubmission) -> NotificationResponse:
    # Placeholder - similar to tile challenge but might have different rewards or logic
    tile = SP3EventTiles.query.filter(SP3EventTiles.id == save.currentTile).first()
    if not tile: return None
    region = SP3Regions.query.filter(SP3Regions.id == tile.region_id).first()
    if not region: return None

    coins_earned = challenge_mapping.data.get("coins", 5) if challenge_mapping.data else 5 # Get from mapping data
    save.coins += coins_earned
    # This type of challenge might not complete the tile on its own if other TILE challenges exist
    # save.isTileCompleted = True 

    fields = [
        NotificationField(name="Coins Earned", value=coins_earned, inline=True),
        NotificationField(name="Total Coins", value=save.coins, inline=True),
    ]
    return NotificationResponse(
        threadId=event.thread_id,
        title=f"{submission.rsn} completed a Coin Challenge!",
        description=f"You earned {coins_earned} coins on tile {tile.name}!",
        color=0xDAA520, # Gold color
        author=NotificationAuthor(name=f"{team.name}: {tile.name} ({region.name})", icon_url=team.image if team.image else None),
        fields=fields,
    )

def progress_region_challenge(challenge: uuid.UUID, event: Events, team: EventTeams, save: SaveData, submission: EventSubmission) -> NotificationResponse:
    challenge = EventChallenges.query.filter(EventChallenges.id == challenge).first()
    if challenge is None:
        logging.warning(f"Challenge definition not found for ID {challenge}")
        return None
    
    # Ensure tileProgress structure exists for the current challenge
    challenge_id_str = str(challenge.id)
    if challenge_id_str not in save.tileProgress:
        save.tileProgress[challenge_id_str] = {}

    made_progress_on_a_task = False
    for task_id_str in challenge.tasks:
        task = EventTasks.query.filter(EventTasks.id == task_id_str).first()
        if not task:
            logging.warning(f"Task definition {task_id_str} not found for challenge {challenge_id_str}")
            continue

        # Ensure progress structure for this task
        if str(task.id) not in save.tileProgress[challenge_id_str]:
            save.tileProgress[challenge_id_str][str(task.id)] = 0
        
        task_matched_submission = False
        for trigger_id_str in task.triggers:
            trigger = EventTriggers.query.filter(EventTriggers.id == trigger_id_str).first()
            if not trigger:
                logging.warning(f"Trigger definition {trigger_id_str} not found for task {task_id_str}")
                continue

            # Normalize source for comparison
            trigger_source_norm = trigger.source.lower() if trigger.source else ""
            submission_source_norm = submission.source.lower() if submission.source else ""
            
            # If trigger source is empty, it can match any submission source (wildcard)
            # OR if trigger source is specified, it must match submission source
            source_matches = (not trigger_source_norm) or (trigger_source_norm == submission_source_norm)

            if trigger.trigger.lower() == submission.trigger.lower() and source_matches:
                task_matched_submission = True
                break

        if task_matched_submission:
            made_progress_on_a_task = True
            current_progress = save.tileProgress[challenge_id_str].get(str(task.id), 0)
            new_progress = current_progress + submission.quantity
            save.tileProgress[challenge_id_str][str(task.id)] = new_progress
            logging.info(f"Team {team.id} progressed task {task.id} for challenge {challenge.id} to {new_progress}/{task.quantity}")

            # Check if this specific task completion completes the challenge (for OR type)
            # For AND type, is_challenge_completed will check all tasks.
            if is_challenge_completed(challenge, task, save):
                logging.info(f"Challenge {challenge.id} (type: {challenge.type}) completed by team {team.id} due to task {task.id} progress.")

                challenges = get_region_challenges(save)
                for challenge_id in challenges:
                    tasks = EventChallenges.query.filter_by(id=challenge_id).first().tasks
                    if challenge_id not in save.tileProgress:
                        save.tileProgress[str(challenge_id)] = {}

                    for task_id in tasks:
                        save.tileProgress[str(challenge_id)][str(task_id)] = 0 # Reset task progress for the challenge

                return create_region_challenge_notification(challenge, event, team, save, submission)
            
    return None

def progress_tile_challenge(challengeMapping: SP3EventTileChallengeMapping, event: Events, team: EventTeams, save: SaveData, submission: EventSubmission) -> NotificationResponse:
    challenge = EventChallenges.query.filter(EventChallenges.id == challengeMapping.challenge_id).first()
    if challenge is None:
        logging.warning(f"Challenge definition not found for ID {challengeMapping.challenge_id}")
        return None
    
    # Ensure tileProgress structure exists for the current challenge
    challenge_id_str = str(challenge.id)
    if challenge_id_str not in save.tileProgress:
        save.tileProgress[challenge_id_str] = {}

    made_progress_on_a_task = False
    for task_id_str in challenge.tasks:
        task = EventTasks.query.filter(EventTasks.id == task_id_str).first()
        if not task:
            logging.warning(f"Task definition {task_id_str} not found for challenge {challenge_id_str}")
            continue

        # Ensure progress structure for this task
        if str(task.id) not in save.tileProgress[challenge_id_str]:
            save.tileProgress[challenge_id_str][str(task.id)] = 0
        
        task_matched_submission = False
        for trigger_id_str in task.triggers:
            trigger = EventTriggers.query.filter(EventTriggers.id == trigger_id_str).first()
            if not trigger:
                logging.warning(f"Trigger definition {trigger_id_str} not found for task {task_id_str}")
                continue

            # Normalize source for comparison
            trigger_source_norm = trigger.source.lower() if trigger.source else ""
            submission_source_norm = submission.source.lower() if submission.source else ""
            
            # If trigger source is empty, it can match any submission source (wildcard)
            # OR if trigger source is specified, it must match submission source
            source_matches = (not trigger_source_norm) or (trigger_source_norm == submission_source_norm)

            if trigger.trigger.lower() == submission.trigger.lower() and source_matches:
                task_matched_submission = True
                break # Found a matching trigger for this task

        if task_matched_submission:
            made_progress_on_a_task = True
            current_progress = save.tileProgress[challenge_id_str].get(str(task.id), 0)
            new_progress = current_progress + submission.quantity
            save.tileProgress[challenge_id_str][str(task.id)] = new_progress
            logging.info(f"Team {team.id} progressed task {task.id} for challenge {challenge.id} to {new_progress}/{task.quantity}")

            # Check if this specific task completion completes the challenge (for OR type)
            # For AND type, is_challenge_completed will check all tasks.
            if is_challenge_completed(challenge, task, save): # Pass the specific task that got progress
                logging.info(f"Challenge {challenge.id} (type: {challenge.type}) completed by team {team.id} due to task {task.id} progress.")
                match challengeMapping.type: # This is the type from SP3EventTileChallengeMapping
                    case "REGION":
                        # Region challenges might not directly complete a tile, handle separately
                        return create_region_challenge_notification(challenge, event, team, save, submission)
                    case "TILE":
                        return create_tile_challenge_notification(challengeMapping, event, team, save, submission)
                    case "COIN":
                        return create_coin_challenge_notification(challengeMapping, event, team, save, submission)
                    # Add other mapping types if necessary
                break # Challenge completed, no need to check other tasks for this submission for this challenge
    
    if made_progress_on_a_task:
        # If progress was made, but challenge not yet completed (e.g. AND type needing more tasks)
        # we might still want to notify or just save progress.
        # For now, notification only on full challenge completion.
        pass

    return None # No notification if challenge not completed by this submission

def get_region_challenges(save: SaveData):
    region = SP3Regions.query.filter(SP3Regions.id == save.islandId).first()
    if not region:
        logging.error(f"Region not found for islandId {save.islandId} during challenge retrieval.")
        return []
    
    return region.challenges if region.challenges else []

def progress_team(event: Events, team: EventTeams, save: SaveData, submission: EventSubmission) -> list[NotificationResponse]:
    notifications: list[NotificationResponse] = []
    if save.currentTile is None:
        logging.warning(f"Team {team.id} has no currentTile, cannot progress challenges.")
        return notifications
    
    for challenge in get_region_challenges(save):
        notif = progress_region_challenge(challenge, event, team, save, submission)
        if notif is not None:
            notifications.append(notif)
            # If a REGION type challenge completed, we might want to stop processing other challenges
            # on this tile for this submission.
            return notifications # We are stopping processing for other challenges here. In the future we can add a flag to progress other tiles with the submission but not complete anything

    for challenge_mapping in get_team_challenges(save): # This gets challenges for the current tile
        notif = progress_tile_challenge(challenge_mapping, event, team, save, submission)
        if notif is not None:
            notifications.append(notif)
            # If a TILE type challenge mapping completed the tile, subsequent challenges on this tile for THIS submission
            # might not be processed if is_team_accepting_submissions now returns False.
            # This depends on the exact game flow desired.
            if save.isTileCompleted and challenge_mapping.type == "TILE":
                 logging.info(f"Tile {save.currentTile} completed by challenge {challenge_mapping.challenge_id}. Further challenge processing for this submission on this tile might be skipped.")
                 # break # Optional: if only one TILE challenge can complete the tile per submission.
    return notifications

def progress_event(event: Events, submission: EventSubmission) -> None:
    # Placeholder for global event progression logic if any
    return None

def is_team_accepting_submissions(save: SaveData) -> bool:
    # Team accepts submissions if their current tile is not yet marked as completed.
    return not save.isTileCompleted

def is_game_accepting_submissions(event: Events) -> bool:
    # Placeholder for global game state checks (e.g., event paused)
    return True # For now, assume game always accepts if event is active

def get_team_from_rsn(eventId: uuid.UUID, rsn: str) -> EventTeams:
    # Case-insensitive search for RSN in EventTeamMemberMappings
    team_mapping = EventTeamMemberMappings.query.filter(
        EventTeamMemberMappings.event_id == eventId,
        EventTeamMemberMappings.username.ilike(rsn) # Use ilike for case-insensitive
    ).first()
    if team_mapping is None:
        return None
    return EventTeams.query.filter(EventTeams.id == team_mapping.team_id).first()

def get_team_from_discord_id(eventId: uuid.UUID, discord_id: str) -> EventTeams:
    if discord_id is None or discord_id == "":
        logging.warning(f"Discord ID is None or empty for event {eventId}. Cannot find team.")
        return None
    # Case-insensitive search for Discord ID in EventTeamMemberMappings
    team_mapping = EventTeamMemberMappings.query.filter(
        EventTeamMemberMappings.event_id == eventId,
        EventTeamMemberMappings.discord_id.ilike(discord_id) # Use ilike for case-insensitive
    ).first()
    if team_mapping is None:
        return None
    return EventTeams.query.filter(EventTeams.id == team_mapping.team_id).first()

def stability_party_handler(submission: EventSubmission) -> list[NotificationResponse]:
    now = datetime.now(timezone.utc)
    event = Events.query.filter(
        Events.start_time <= now, 
        Events.end_time >= now, 
        Events.type == "STABILITY_PARTY"
    ).first()

    if event is None:
        logging.info(f"No active STABILITY_PARTY event found for submission by {submission.rsn}.")
        return None # Or an empty list

    team = get_team_from_rsn(event.id, submission.rsn)
    if team is None:
        team = get_team_from_discord_id(event.id, submission.id)
    
    if team is None:
        logging.info(f"Team not found for RSN '{submission.rsn}' or ID '{submission.id}' in event '{event.name}' (ID: {event.id}).")
        return None
    
    if event.data.get("log") is None:
        event.data["log"] = {} # Ensure log is initialized

    if event.data["log"].get(submission.trigger) is None:
        event.data["log"][submission.trigger] = {
            "value": submission.totalValue,
            "quantity": submission.quantity
        }
    else:
        event.data["log"][submission.trigger] = {
            "value": event.data["log"][submission.trigger]["value"] + submission.totalValue,
            "quantity": event.data["log"][submission.trigger]["quantity"] + submission.quantity
        }

    flag_modified(event, "data") # Flag the event data as modified
    db.session.commit() # Commit the event data changes

    # Ensure team.data is not None before passing to SaveData.from_dict
    team_data_dict = team.data if team.data is not None else {}
    save = SaveData.from_dict(team_data_dict)

    if save.currentTile is None:
        logging.warning(f"Team {team.name} (ID: {team.id}) has no currentTile. Submissions cannot be processed for challenges yet.")
        # Potentially, they might be submitting something that *gives* them their first tile,
        # but standard challenge progression requires a currentTile.
        return None # Or handle specific "pre-game" submissions if any

    if not is_game_accepting_submissions(event): # Global check
        logging.info(f"Game (event {event.name}) is not currently accepting submissions.")
        return None

    if not is_team_accepting_submissions(save): # Team-specific check
        logging.info(f"Team {team.name} (ID: {team.id}) is not accepting submissions (tile {save.currentTile} likely completed or action pending).")
        return None

    notifications = progress_team(event, team, save, submission)
    
    # progress_event might be for global, non-team specific objectives
    # progress_event(event, submission) 
    
    save_team_data(team, save) # Save any changes to save.data (like tileProgress, coins, isTileCompleted)

    return notifications

def roll_dice_progression(event_id_str: str, team_id_str: str, data: dict = None, action_type: str = None, action_choice: str = None):
    """
    Master function for handling dice roll progression.
    Handles initial roll, island selection, and subsequent moves/actions.
    """
    try:
        event_id = uuid.UUID(event_id_str)
        team_id = uuid.UUID(team_id_str)
    except ValueError:
        logging.error(f"Invalid UUID format for event_id or team_id. Event: {event_id_str}, Team: {team_id_str}")
        return {"error": "Invalid event or team ID format."}, 400

    logging.info(f"Roll progression request: event_id={event_id}, team_id={team_id}, action_type={action_type}")
    if data: logging.debug(f"Roll progression input data: {data}")

    event = Events.query.filter_by(id=event_id, type="STABILITY_PARTY").first()
    if not event:
        logging.error(f"Event not found or not a SP3 event: {event_id}")
        return {"error": "Event not found or not a Stability Party event"}, 404
    
    team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
    if not team:
        logging.error(f"Team not found for event: team_id={team_id}, event_id={event_id}")
        return {"error": "Team not found or does not belong to this event"}, 404
    
    team_data_dict = team.data if team.data is not None else {}
    save = SaveData.from_dict(team_data_dict)
    
    logging.debug(f"Initial team state: currentTile={save.currentTile}, isRolling={save.isRolling}, isTileCompleted={save.isTileCompleted}")
    
    response_payload = {}

    try:
        if action_type is None: 
            if save.currentTile is None: 
                logging.info(f"Team {team_id} has no currentTile. Initiating FIRST_ROLL sequence.")
                roll_state_obj = _handle_first_roll_initiation(event_id, team_id, save, data if data else {})
                response_payload = roll_state_obj.to_dict()
                save_team_data(team, save) 
                return response_payload, 200
            else: 
                logging.info(f"Initiating new standard roll for team {team_id}")
                if not save.isTileCompleted:
                    logging.error(f"Cannot roll - current tile not completed: team={team_id}, tile={save.currentTile}")
                    return {"error": "Current tile must be completed before rolling"}, 400
                if save.isRolling:
                    logging.error(f"Cannot roll - team is already in a rolling sequence: team={team_id}")
                    return {"error": "Team is already in a rolling sequence. Complete current action."}, 400
                
                _initiate_new_roll(event_id, team_id, save, data if data else {})
                response_payload = _process_next_move(event_id, team_id, save)
                save_team_data(team, save)
                return response_payload, 200

        elif action_type == RollState.ACTION_TYPES["ISLAND_SELECTION"]:
            logging.info(f"Processing ISLAND_SELECTION for team {team_id}")
            if not save.isRolling: # Should be true if they were prompted for FIRST_ROLL
                 logging.error(f"Cannot process island selection - team not in a rolling/pending state: team={team_id}")
                 return {"error": "Not currently awaiting an island selection."}, 400
            if save.currentTile is not None: # Should be None if they are selecting their first island
                 logging.error(f"Cannot process island selection - team already has a current tile: {save.currentTile}")
                 return {"error": "Island selection is only for the first move."}, 400

            response_payload = _handle_island_selection(event_id, team_id, save, data if data else {})
            if "error" in response_payload: 
                return response_payload, response_payload.get("status_code", 400) 
            save_team_data(team, save)
            return response_payload, 200
            
        # --- Existing Action Handlers ---
        # Ensure team is in a rolling state for these actions
        elif not save.isRolling: # This check applies to SHOP, STAR, DOCK, CROSSROAD, CONTINUE
            logging.error(f"Cannot process action '{action_type}' - no roll in progress for team {team_id}")
            return {"error": f"No roll in progress to perform action: {action_type}"}, 400

        elif action_type == RollState.ACTION_TYPES["SHOP"]:
            response_payload = _handle_shop_action(event_id, team_id, save, data if data else {})
        elif action_type == RollState.ACTION_TYPES["STAR"]:
            response_payload = _handle_star_action(event_id, team_id, save, data if data else {})
        elif action_type == RollState.ACTION_TYPES["DOCK"]:
            response_payload = _handle_dock_action(event_id, team_id, save, data if data else {})
        elif action_type == RollState.ACTION_TYPES["CROSSROAD"]:
            response_payload = _handle_crossroad_action(event_id, team_id, save, data if data else {})
        elif action_type == RollState.ACTION_TYPES["CONTINUE"]:
            current_roll_remaining = save.roll_state.roll_remaining
            if current_roll_remaining <= 0:
                logging.warning(f"Continue action called with roll_remaining <= 0 for team {team_id}. Completing roll.")
                # Update roll state with current values
                if save.roll_state:
                    save.roll_state.roll_remaining = 0
                else:
                    save.roll_state = RollState(event_id, team_id, 0, save.currentTile)
                    save.roll_state.roll_remaining = 0
                
                response_payload = _complete_roll(event_id, team_id, save)
            else:
                # Update roll state with current values
                if save.roll_state:
                    save.roll_state.roll_remaining = current_roll_remaining
                else:
                    save.roll_state = RollState(event_id, team_id, current_roll_remaining, save.currentTile)
                    save.roll_state.roll_remaining = current_roll_remaining
                
                response_payload = _process_next_move(event_id, team_id, save)
        else:
            logging.error(f"Unknown or unhandled action type received: {action_type}")
            return {"error": f"Unknown or unhandled action type: {action_type}"}, 400

        # Save data after any action that modified 'save' object and did not error
        if "error" not in response_payload:
            logging.info(f"Action '{action_type}' processed successfully for team {team_id}. Saving state.")
            save_team_data(team, save)
        else:
            logging.error(f"Error processing action '{action_type}' for team {team_id}: {response_payload['error']}")
        
        status_code = 400 if "error" in response_payload else 200
        return response_payload, status_code
            
    except Exception as e:
        db.session.rollback() 
        logging.error(f"Critical error in roll_dice_progression: {str(e)}", exc_info=True)
        return {"error": "An internal server error occurred during roll progression."}, 500

def _initiate_new_roll(event_id, team_id, save: SaveData, data: dict) -> None:
    logging.info(f"Initiating new standard roll for team {team_id}")
    
    dice_sides_to_roll = save.dice if save.dice else [6] 
    modifier_val = save.modifier if save.modifier is not None else 0
    
    dice_results = []
    for sides in dice_sides_to_roll:
        try:
            dice_results.append(random.randint(1, int(sides)))
        except ValueError:
            logging.warning(f"Invalid dice side value '{sides}' for team {team_id}, defaulting to D6.")
            dice_results.append(random.randint(1, 6))
            
    try:
        roll_total = sum(dice_results) + int(modifier_val)
    except (ValueError, TypeError):
        roll_total = sum(dice_results)
        modifier_val = 0
        logging.warning(f"Invalid modifier, defaulting to sum of dice: {roll_total}")

    region = SP3Regions.query.filter(SP3Regions.id == save.islandId).first()
    if region.data.get("isHotspot", False):
        # Check to see if the island is "Mountain Mayhem"
        if region.name == "Mountain Mayhem" and save.islandLaps == 0:
            # We are in "Mountain Mode". Every roll will be a 1.
            roll_total = 1
            dice_results = [1]
            modifier_val = 0
            team = EventTeams.query.filter_by(id=team_id).first()
            logging.info(f"Mountain Mayhem active. Roll total set to 1 for team {team.name} ({team_id}).")
    
    save.roll_state = RollState(event_id, team_id, roll_total, save.currentTile)
    save.roll_state.dice_results_for_roll = dice_results
    save.roll_state.modifier_for_roll = modifier_val
    
    save.previousTile = save.currentTile
    save.isRolling = True 
    save.isTileCompleted = False
    
    logging.info(f"Team {team_id} initiated roll. Results: {dice_results}, Mod: {modifier_val}, Total: {roll_total}. Current Tile: {save.currentTile}")

def _process_next_move(event_id, team_id, save: SaveData) -> dict:
    logging.info(f"Processing next move for team {team_id}. Roll remaining: {save.roll_state.roll_remaining}, Current Tile: {save.currentTile}")

    if save.roll_state.roll_remaining <= 0:
        logging.debug(f"No moves remaining for team {team_id}. Completing roll.")
        return _complete_roll(event_id, team_id, save)

    current_tile_obj = SP3EventTiles.query.filter_by(id=save.currentTile).first()
    if not current_tile_obj:
        logging.error(f"Current tile {save.currentTile} not found for team {team_id}.")
        save.isRolling = False 
        return {"error": "Current tile not found, cannot process move."}

    if not save.roll_state.path_taken_this_turn or save.roll_state.path_taken_this_turn[-1] != save.currentTile:
        save.roll_state.path_taken_this_turn.append(save.currentTile)

    next_tile_ids_str = current_tile_obj.data.get("nextTiles", []) if current_tile_obj.data else []

    if len(next_tile_ids_str) > 1:
        logging.info(f"Crossroad detected at tile {current_tile_obj.id} for team {team_id}.")
        return _handle_crossroad(event_id, team_id, save, next_tile_ids_str)
    elif len(next_tile_ids_str) == 1:
        next_tile_id_str = next_tile_ids_str[0]
        logging.info(f"Team {team_id} moving from {current_tile_obj.id} to single next tile {next_tile_id_str}.")
        
        save.currentTile = uuid.UUID(next_tile_id_str)
        save.roll_state.current_tile_id = save.currentTile
        save.roll_state.roll_remaining -= 1
        
        logging.debug(f"Team {team_id} moved to {save.currentTile}. Roll remaining: {save.roll_state.roll_remaining}")
        return _check_for_special_tile(event_id, team_id, save)
    else: 
        logging.info(f"No next tiles from {current_tile_obj.id} for team {team_id}. Completing roll.")
        return _complete_roll(event_id, team_id, save)

def is_star_tile(tile_id):
    """Check if the tile is a star tile"""
    tile = SP3EventTiles.query.filter_by(id=tile_id).first()
    if tile:
        event = Events.query.filter_by(id=tile.event_id).first()
        if event:
            star_list = event.data.get("star_tiles", [])
            if str(tile_id) in star_list:
                logging.debug(f"Tile {tile_id} is a star tile")
                return True
            else:
                logging.debug(f"Tile {tile_id} is not a star tile")
                return False
            
    return False

def is_dock_tile(tile_id):
    """Check if the tile is a dock tile"""
    tile = SP3EventTiles.query.filter_by(id=tile_id).first()
    if tile:
        isDock = tile.data.get("isDock", False)
        if isDock:
            logging.debug(f"Tile {tile_id} is a dock tile")
            return True
        else:
            logging.debug(f"Tile {tile_id} is not a dock tile")
            return False
            
    return False

def is_shop_tile(tile_id):
    """Check if the tile is a shop tile"""
    tile = SP3EventTiles.query.filter_by(id=tile_id).first()
    if tile:
        isShop = tile.data.get("isShop", False)
        if isShop:
            logging.debug(f"Tile {tile_id} is a shop tile")
            return True
        else:
            logging.debug(f"Tile {tile_id} is not a shop tile")
            return False
            
    return False

def is_island_start_tile(tile_id):
    """Check if the tile is the first tile of an island"""
    tile = SP3EventTiles.query.filter_by(id=tile_id).first()
    if tile:
        isIslandStart = tile.data.get("isIslandStart", False)
        if isIslandStart:
            logging.debug(f"Tile {tile_id} is the start tile of an island")
            return True
        else:
            logging.debug(f"Tile {tile_id} is not the start tile of an island")
            return False
            
    return False

def is_region_populated(tile_id):
    """Check if the tile is a populated region"""
    all_teams: list[EventTeams] = EventTeams.query.all()
    tile = SP3EventTiles.query.filter_by(id=tile_id).first()
    if not tile:
        logging.error(f"Tile not found for ID {tile_id}")
        return False
    
    tile_region_id = tile.region_id
    for team in all_teams:
        if team.data.get("islandId") == str(tile_region_id):
            logging.debug(f"Tile {tile_id} is a populated region")
            return True
            
    return False

def does_region_have_star(tile_id):
    """Check if the tile is a region with a star"""
    tile = SP3EventTiles.query.filter_by(id=tile_id).first()
    tile_region = tile.region_id if tile else None
    if tile and tile_region:
        event = Events.query.filter_by(id=tile.event_id).first()
        if event:
            star_list = event.data.get("star_tiles", [])
            for star_tile_id in star_list:
                star_tile = SP3EventTiles.query.filter_by(id=star_tile_id).first()
                star_tile_region = star_tile.region_id if star_tile else None
                if str(tile_region) == str(star_tile_region):
                    logging.debug(f"Tile {tile_id} is a region with a star")
                    return True
            
    return False

def _check_for_special_tile(event_id, team_id, save):
    """Check if the current tile is a special tile that needs interaction"""
    logging.info(f"Checking for special tile interaction for team {team_id} at tile {save.currentTile}")
    
    current_tile = SP3EventTiles.query.filter_by(id=save.currentTile).first()
    if not current_tile:
        logging.error(f"Current tile not found: {save.currentTile}")
        return {"error": "Current tile not found"}
    
    logging.debug(f"Current tile details: name={current_tile.name}, id={current_tile.id}")
    
    # Get info about the tile
    tile_info = {
        "id": str(current_tile.id),
        "name": current_tile.name,
        "description": current_tile.description
    }
    
    # Check if we need to set island ID based on the tile
    if current_tile.region_id and current_tile.region_id != save.islandId:
        logging.info(f"Updating team island ID from {save.islandId} to {current_tile.region_id}")
        save.islandId = current_tile.region_id
    
    # Check if this is a special tile that requires an action
    if is_shop_tile(current_tile.id):
        logging.info(f"Special tile detected: SHOP - Preparing shop interaction")
        return _prepare_shop_interaction(event_id, team_id, save, current_tile)
    elif is_star_tile(current_tile.id):
        logging.info(f"Special tile detected: STAR_SPOT - Preparing star interaction")
        return _prepare_star_interaction(event_id, team_id, save, current_tile)
    elif is_dock_tile(current_tile.id):
        logging.info(f"Special tile detected: DOCK - Preparing dock interaction")
        return _prepare_dock_interaction(event_id, team_id, save, current_tile)
    else:
        logging.info(f"Regular tile no special interaction required")
        
        # Regular tile, continue movement automatically if there are moves left
        if save.roll_state.roll_remaining > 0:
            logging.debug(f"Moves remaining: {save.roll_state.roll_remaining}, automatically continuing to next tile")
            
            # Add current tile to the response for client information
            # Handle the case where path_taken_this_turn might not exist
            if not hasattr(save.roll_state, 'path_taken_this_turn'):
                logging.warning(f"Creating missing path_taken_this_turn attribute on roll_state for team {team_id}")
                save.roll_state.path_taken_this_turn = []
            
            save.roll_state.path_taken_this_turn.append(save.currentTile)
            
            # Automatically continue to the next tile
            return _process_next_move(event_id, team_id, save)
        else:
            logging.debug("No moves remaining, completing roll")
            # No more moves left, finalize the roll
            return _complete_roll(event_id, team_id, save)
    
    return save.roll_state.to_dict()

def _handle_crossroad(event_id, team_id, save: SaveData, next_tile_ids_str: list) -> dict:
    logging.info(f"Handling crossroad for team {team_id} with {len(next_tile_ids_str)} options")
    current_tile_obj = SP3EventTiles.query.filter_by(id=save.currentTile).first()
    path_options = []
    for tile_id_str in next_tile_ids_str:
        next_tile = SP3EventTiles.query.filter_by(id=uuid.UUID(tile_id_str)).first()
        if next_tile:
            path_options.append({"id": str(next_tile.id), "name": next_tile.name, "description": next_tile.description or ""})
    
    save.roll_state.action_required = RollState.ACTION_TYPES["CROSSROAD"]
    save.roll_state.action_data = {
        "message": "Choose your path!",
        "current_tile": {"id": str(current_tile_obj.id), "name": current_tile_obj.name} if current_tile_obj else None,
        "options": path_options,
        "roll_remaining": save.roll_state.roll_remaining 
    }
    return save.roll_state.to_dict()

def _handle_crossroad_action(event_id, team_id, save: SaveData, data: dict) -> dict:
    chosen_next_tile_id_str = data.get("directionId")
    roll_remaining_from_client = save.roll_state.roll_remaining

    if not chosen_next_tile_id_str: return {"error": "No tile chosen at crossroad"}, 400
    
    save.currentTile = uuid.UUID(chosen_next_tile_id_str)
    
    # Update roll state
    if save.roll_state:
        save.roll_state.current_tile_id = save.currentTile
        save.roll_state.roll_remaining = roll_remaining_from_client - 1
    else:
        save.roll_state = RollState(event_id, team_id, roll_remaining_from_client, save.currentTile)
        save.roll_state.roll_remaining = roll_remaining_from_client - 1
    
    return _check_for_special_tile(event_id, team_id, save)

def _prepare_shop_interaction(event_id, team_id, save, current_tile):
    logging.info(f"Preparing SHOP for team {team_id} at {current_tile.name}")
    save.roll_state.action_required = RollState.ACTION_TYPES["SHOP"]
    # Actual shop items would be generated here

    items = generate_shop_inventory(event_id, shop_tier=1, item_count=3)

    # get region name
    region = SP3Regions.query.filter(SP3Regions.id == current_tile.region_id).first()
    if region:
        region_name = region.name
    else:
        region_name = "Unknown Region"

    save.roll_state.action_data = {
        "message": f"Welcome to the {region_name} shop!",
        "team_items": save.itemList,
        "items": items,
        "coins": save.coins,
        "moves_remaining": save.roll_state.roll_remaining,
    }

    return save.roll_state.to_dict()

def _handle_shop_action(event_id, team_id, save, data):
    logging.info(f"Team {team_id} shop action: {data}")

    action = data.get("action")
    if action != "buy": # Can extend this to other actions if needed
        logging.error(f"Invalid action for shop interaction: {action}")
        return {"error": "Invalid action for shop interaction"}, 400
    
    purchased_item_id = data.get("itemId")
    purchased_item_price = data.get("price")

    if purchased_item_id is None:
        logging.error("No item ID provided for purchase.")
        return {"error": "No item ID provided for purchase"}, 400
    
    if purchased_item_price is None:
        logging.error("No price provided for purchased item.")
        return {"error": "No price provided for purchased item"}, 400
    
    # Check if the team has enough coins
    if save.coins < purchased_item_price:
        logging.error(f"Not enough coins to purchase item {purchased_item_id}. Required: {purchased_item_price}, Available: {save.coins}")
        return {"error": "Not enough coins to purchase item"}, 400
    
    # Check the team's amount of items
    if len(save.itemList) >= 3:
        logging.error(f"Cannot purchase item {purchased_item_id} - inventory full (3 items max).")
        return {"error": "Inventory full (3 items max)"}, 400
    
    # Deduct coins for the purchase
    save.coins -= purchased_item_price
    item = get_item_by_id(purchased_item_id) # Placeholder for actual item retrieval logic
    logging.info(f"Team {team_id} purchased item {item.get("name")} for {purchased_item_price} coins. Remaining coins: {save.coins}")

    add_item_to_inventory(event_id, team_id, purchased_item_id)

    send_event_notification(event_id, team_id, "Item Purchased!", f"purchased {item.get('name')} for {purchased_item_price} coins!")

    roll_remaining_from_client = save.roll_state.roll_remaining
    # Update roll state
    if save.roll_state:
        save.roll_state.roll_remaining = roll_remaining_from_client
    else:
        save.roll_state = RollState(event_id, team_id, roll_remaining_from_client, save.currentTile)
        save.roll_state.roll_remaining = roll_remaining_from_client
    
    logging.info(f"After shop interaction, maintaining roll remaining: {roll_remaining_from_client}")
    
    if save.roll_state.roll_remaining > 0:
        return _process_next_move(event_id, team_id, save)
    return _complete_roll(event_id, team_id, save)

def _prepare_star_interaction(event_id, team_id, save, current_tile):
    logging.info(f"Preparing STAR for team {team_id} at {current_tile.name}")
    save.roll_state.action_required = RollState.ACTION_TYPES["STAR"]
    save.roll_state.action_data = {
        "message": f"Star available at {current_tile.name}!",
        "price": 100,
        "roll_remaining": save.roll_state.roll_remaining,
        "coins": save.coins
    }
    return save.roll_state.to_dict()

def _handle_star_action(event_id, team_id, save, data):
    logging.info(f"Team {team_id} star action: {data}")
    # Actual star purchase logic
    roll_remaining_from_client = save.roll_state.roll_remaining

    if data.get("action") == "buy":
        if save.coins < 100:
            logging.error(f"Not enough coins to purchase star. Required: 100, Available: {save.coins}. Progressing anyways...")
            
            if save.roll_state.roll_remaining > 0:
                return _process_next_move(event_id, team_id, save)
            return _complete_roll(event_id, team_id, save)
        
        if not is_star_tile(save.currentTile):
            logging.error(f"Current tile {save.currentTile} is not a star tile.")
            return {"error": "Current tile is not a star tile"}, 400
        
        # Deduct coins for the star purchase
        save.coins -= 100
        save.stars += 1

        # Move the star to a new tile
        new_star_tile_id = None
        all_regions = SP3Regions.query.all()
        applicable_regions = []

        for region in all_regions:
            if not is_region_populated(region.id):
                applicable_regions.append(region.id)
                
        applicable_region_tiles = SP3EventTiles.query.filter(
            SP3EventTiles.event_id == event_id,
            SP3EventTiles.region_id.in_(applicable_regions),
        ).all()
        for region in all_regions:
            if not is_region_populated(region.id):
                applicable_regions.append(region.id)
                
        applicable_region_tiles = SP3EventTiles.query.filter(
            SP3EventTiles.event_id == event_id,
            SP3EventTiles.region_id.in_(applicable_regions),
        ).all()

        # Filter out tiles that are shops, docks, or already have stars
        applicable_region_tiles = [tile for tile in applicable_region_tiles if not is_shop_tile(tile.id) and not is_dock_tile(tile.id) and not is_star_tile(tile.id)]
        logging.info(f"Applicable region tiles for star placement: {[tile.name for tile in applicable_region_tiles]}")
        if applicable_region_tiles:
            new_star_tile = random.choice(applicable_region_tiles)
            new_star_tile_id = new_star_tile.id
            logging.info(f"Star moved to tile {new_star_tile.name} (ID: {new_star_tile_id})")
        else:
            logging.error("No valid tiles available for star placement.")
            return {"error": "No valid tiles available for star placement"}, 400
        
        old_star_tile_id = save.currentTile
        event = Events.query.filter_by(id=event_id).first()
        star_tiles = event.data.get("star_tiles")
        star_tiles.remove(str(old_star_tile_id))
        star_tiles.append(str(new_star_tile_id))
        event.data["star_tiles"] = star_tiles
        flag_modified(event, "data")
        db.session.commit()

        team_name = EventTeams.query.filter_by(id=team_id).first().name
        old_star_tile = SP3EventTiles.query.filter_by(id=old_star_tile_id).first()
        old_star_tile_name = old_star_tile.name
        old_star_tile_region = SP3Regions.query.filter_by(id=old_star_tile.region_id).first().name
        new_star_tile = SP3EventTiles.query.filter_by(id=new_star_tile_id).first()
        new_star_tile_name = new_star_tile.name
        new_star_tile_region = SP3Regions.query.filter_by(id=new_star_tile.region_id).first().name
        send_event_notification(event_id, team_id, f"{team_name} has purchased a star!", f"purchased the star on {old_star_tile_name} on {old_star_tile_region}!\n\nThe star has been moved to {new_star_tile_name} on {new_star_tile_region}!")

    # Update roll state
    if not save.roll_state:
        save.roll_state = RollState(event_id, team_id, roll_remaining_from_client, save.currentTile)
        
    save.roll_state.roll_remaining = roll_remaining_from_client
    
    logging.info(f"After star interaction, maintaining roll remaining: {roll_remaining_from_client}")
    
    if save.roll_state.roll_remaining > 0:
        return _process_next_move(event_id, team_id, save)
    return _complete_roll(event_id, team_id, save)

def _island_lap_completed(event_id, team_id, save: SaveData):
    """Check if the team has completed a lap around the island"""
    logging.info(f"Checking if team {team_id} has completed an island lap.")
    if save.islandLaps is None:
        save.islandLaps = 0

    # Check if the current tile is the start tile of the island
    save.islandLaps += 1
    logging.info(f"Team {team_id} completed an island lap. Total laps: {save.islandLaps}")

    # Check for island hotspot
    region = SP3Regions.query.filter(SP3Regions.id == save.islandId).first()
    is_hotspot = region.data.get("isHotspot", False) if region else False
    if is_hotspot:
        # Each island has its own hotspot logic...
        logging.info(f"Looking for region name: {region.name}")
        match region.name:
            case "Moonwake Cove":
                if len(save.itemList) >= 3:
                    logging.info("Too many items for hotspot bonus")
                    send_event_notification(event_id, team_id, "Moonwake Cove Hotspot Completion", f"completed a hot zone lap but had too many items and were not able to gain any more!")
                    return

                available_items = get_items_by_rarity("common") + get_items_by_rarity("uncommon")
                print([item.name for item in available_items])
                random_pick = random.choice(available_items)

                add_item_to_inventory(event_id, team_id, random_pick.id)
                send_event_notification(event_id, team_id, "Moonwake Cove Hotspot Completion", f"completed a hot zone lap and received a {random_pick.name}!")
            case "Mountain Mayhem":
                if save.islandLaps > 1:
                    logging.info("Can only complete the mountain challenge once")
                    return
                
                # If the team has completed the mountain challenge, they get a star
                save.stars += 1
                team = EventTeams.query.filter_by(id=team_id).first()
                logging.info(f"Team {team.name} ({team_id}) completed the Mountain Challenge. Added one star to give total stars: {save.stars}")
                send_event_notification(event_id, team_id, "The Mountain Has Been Conquered", f"completed the Mountain Challenge and received a star!\n\nTotal stars: {save.stars}")
            case "Raid-ical Island":
                if save.islandLaps >= 3:
                    logging.info("Can only complete the raid-ical challenge three times")
                    return
                
                # If the team has completed the raid-ical challenge, they get 50 coins
                save.coins += 50
                team = EventTeams.query.filter_by(id=team_id).first()
                logging.info(f"Team {team.name} ({team_id}) completed the Raid-ical Challenge. Added 50 coins to give total coins: {save.coins}")
                send_event_notification(event_id, team_id, "Raid-ical Island Challenge Completed", f"completed the Raid-ical Challenge and received 50 coins!\n\nTotal coins: {save.coins}")


def _prepare_dock_interaction(event_id, team_id, save, current_tile: SP3EventTiles):
    logging.info(f"Preparing DOCK for team {team_id} at {current_tile.name}")
    save.roll_state.action_required = RollState.ACTION_TYPES["DOCK"]

    _island_lap_completed(event_id, team_id, save)

    region = SP3Regions.query.filter(SP3Regions.id == current_tile.region_id).first()
    charter_data = region.data.get("charter", [])
    sailing_ticket = False
    for buff in save.buffs:
        if buff.get("type", "") == "sailing_ticket":
            sailing_ticket = True
            break
    
    destinations = []
    for destination_id, cost in charter_data.items():
        region = SP3Regions.query.filter(SP3Regions.id == destination_id).first()
        destination = {
            "id": destination_id,
            "name": region.name,
            "description": region.description,
            "cost": cost if not sailing_ticket else 0,
        }
        destinations.append(destination)

    # Actual destination list generation
    save.roll_state.action_data = {
        "message": f"Dock available at {current_tile.name}. Charter options...",
        "destinations": destinations,
        "roll_remaining": save.roll_state.roll_remaining,
        "coins": save.coins,
    }
    return save.roll_state.to_dict()

def _handle_dock_action(event_id, team_id, save, data):
    """Handle dock interaction, either chartering to new island or continuing movement"""
    logging.info(f"Team {team_id} dock action: {data}")
    
    # Handle chartering to a new island
    if data.get("action", "") == "charter":
        destination_id = data.get("destinationId")
        cost = data.get("cost", 0)
        destination_region = SP3Regions.query.filter(SP3Regions.id == uuid.UUID(destination_id)).first()
        starting_region = SP3Regions.query.filter(SP3Regions.id == save.islandId).first()

        if starting_region.data.get("charter", {}).get(destination_id, 0) != cost:
            sailing_ticket = False
            print(save.buffs)
            for i, buff in enumerate(save.buffs):
                print(buff, i)
                if buff.get("type", "") == "sailing_ticket":
                    sailing_ticket_buff_index = i
                    sailing_ticket = True
                    break
            
            if sailing_ticket and cost == 0:
                # Get the buff reference in the save data
                save.buffs[sailing_ticket_buff_index]["uses"] -= 1
                if save.buffs[sailing_ticket_buff_index]["uses"] <= 0:
                    # Remove the buff if no uses left
                    del save.buffs[sailing_ticket_buff_index]
            else: # Otherwise, they are trying to cheat the system
                logging.error(f"Invalid cost for chartering to {str(destination_id)}. Expected {starting_region.data['charter'][str(destination_id)]}, got {data['cost']}")
                return {"error": "Invalid cost for chartering to new island."}, 400

        # Get the region's start tile
        if destination_region:
            start_tile = db.session.query(SP3EventTiles).filter(
                SP3EventTiles.event_id == event_id,
                SP3EventTiles.region_id == destination_region.id,
                SP3EventTiles.data.has_key('isIslandStart'), 
                SP3EventTiles.data['isIslandStart'].astext.cast(db.Boolean) == True 
            ).first()
            
            if start_tile:
                save.coins -= cost
                save.currentTile = start_tile.id
                save.islandId = destination_region.id
                save.islandLaps = 0

                region = SP3Regions.query.filter(SP3Regions.id == save.islandId).first()
                if region.data.get("isHotspot", False):
                    # Check to see if the island is "Mountain Mayhem"
                    if region.name == "Mountain Mayhem":
                        # We are in "Mountain Mode". Every roll will be a 1.
                        team = EventTeams.query.filter_by(id=team_id).first()
                        logging.info(f"Mountain Mayhem active. Rest of the roll totaling {save.roll_state.roll_remaining} has been reduced to 1, ensuring that we land on tile 1 for team {team.name} ({team_id}).")
                        save.roll_state.roll_remaining = 1
            else:
                logging.error(f"No start tile found for region {destination_region.name} (ID: {destination_region.id})")
                return {"error": "No start tile found for the selected island."}, 400

        # Remove 1 from the roll remaining for the dock interaction
        roll_remaining_from_client = save.roll_state.roll_remaining
        if not save.roll_state:
            save.roll_state = RollState(event_id, team_id, roll_remaining_from_client - 1, save.currentTile)
        
        save.roll_state.roll_remaining = roll_remaining_from_client - 1
        save.roll_state.path_taken_this_turn.append(save.currentTile)

        logging.info(f"Team {team_id} chartered to new island.")
        
        return _process_next_move(event_id, team_id, save)
    
    # Handle skipping the dock / continuing movement
    else: 
        roll_remaining_from_client = data.get("roll_remaining", 0)
        
        # Do NOT consume a move for the dock interaction itself - only movement consumes moves
        if save.roll_state:
            save.roll_state.roll_remaining = roll_remaining_from_client
        else:
            save.roll_state = RollState(event_id, team_id, roll_remaining_from_client, save.currentTile)
            save.roll_state.roll_remaining = roll_remaining_from_client
        
        logging.info(f"After dock interaction (skipped), maintaining roll remaining: {roll_remaining_from_client}")
        
        if save.roll_state.roll_remaining > 0:
            return _process_next_move(event_id, team_id, save)
        return _complete_roll(event_id, team_id, save)

def _handle_first_roll_initiation(event_id: uuid.UUID, team_id: uuid.UUID, save: SaveData, data: dict) -> RollState:
    """Handle the first roll in the game to select a starting island"""
    logging.info(f"Initiating FIRST ROLL for team {team_id} in event {event_id}.")

    dice_to_roll = save.dice if save.dice else [6] 
    modifier_val = save.modifier if save.modifier is not None else 0
    
    dice_results = []
    for d_sides in dice_to_roll:
        try:
            dice_results.append(random.randint(1, int(d_sides)))
        except ValueError:
            logging.warning(f"Invalid dice side value '{d_sides}' for team {team_id}, defaulting to D6.")
            dice_results.append(random.randint(1, 6))

    try:
        roll_total_value = sum(dice_results) + int(modifier_val)
    except (ValueError, TypeError):
        roll_total_value = sum(dice_results)
        modifier_val = 0
    
    logging.info(f"Team {team_id} first roll results: {dice_results}, modifier: {modifier_val}, total: {roll_total_value}")

    available_islands = []
    regions = SP3Regions.query.filter_by(event_id=event_id).order_by(SP3Regions.name).all()
    
    for region in regions:
        start_tile_exists = db.session.query(SP3EventTiles).filter(
            SP3EventTiles.event_id == event_id,
            SP3EventTiles.region_id == region.id,
            SP3EventTiles.data.has_key('isIslandStart'), 
            SP3EventTiles.data['isIslandStart'].astext.cast(db.Boolean) == True 
        ).first()
        
        if start_tile_exists:
            available_islands.append({
                "id": str(region.id), 
                "name": region.name,
                "description": region.description or "An exciting new land!"
            })
        else:
            logging.warning(f"Region {region.name} (ID: {region.id}) has no designated start tile (isIslandStart:true in data).")
    
    save.roll_state = RollState(event_id, team_id, roll_total_value) 
    save.roll_state.dice_results_for_roll = dice_results
    save.roll_state.modifier_for_roll = modifier_val
    save.roll_state.action_required = RollState.ACTION_TYPES["FIRST_ROLL"]
    
    if not available_islands:
        logging.error(f"No available starting islands with start_tile found for event {event_id}.")
        save.roll_state.action_data = {
            "error": "ConfigurationError: No starting islands available. Please contact an admin.",
            "message": "Cannot start the game. No starting locations defined.",
            "dice_results_for_roll": dice_results, 
            "modifier_for_roll": modifier_val,
            "roll_total_for_turn": roll_total_value, 
            "available_islands": []
        }
        save.isRolling = False
    else:
        save.isRolling = True 
        save.isTileCompleted = False
        save.roll_state.action_data = {
            "message": "Welcome! You've taken your first roll. Now, choose your starting island!",
            "dice_results_for_roll": dice_results, 
            "modifier_for_roll": modifier_val,
            "roll_total_for_turn": roll_total_value, 
            "available_islands": available_islands
        }
        
        # Initialize roll state with the total value of the first roll
        # This ensures the player will have their full movement after choosing an island
        save.roll_state.roll_remaining = roll_total_value
    
    return save.roll_state

def _handle_island_selection(event_id: uuid.UUID, team_id: uuid.UUID, save: SaveData, data: dict) -> dict:
    logging.info(f"Handling ISLAND SELECTION for team {team_id} in event {event_id}.")
    chosen_island_id_str = data.get("chosen_island_id")

    if not chosen_island_id_str:
        logging.error(f"Team {team_id} did not provide chosen_island_id.")
        return {"error": "chosen_island_id is required."}

    try:
        chosen_island_id = uuid.UUID(chosen_island_id_str)
    except ValueError:
        logging.error(f"Invalid UUID format for chosen_island_id: {chosen_island_id_str}")
        return {"error": "Invalid island ID format."}

    chosen_region = SP3Regions.query.filter_by(id=chosen_island_id, event_id=event_id).first()
    if not chosen_region:
        logging.error(f"Chosen island ID {chosen_island_id} not found or not part of event {event_id}.")
        return {"error": "Invalid island choice."}

    starting_tile = db.session.query(SP3EventTiles).filter(
        SP3EventTiles.event_id == event_id,
        SP3EventTiles.region_id == chosen_island_id,
        SP3EventTiles.data.has_key('isIslandStart'),
        SP3EventTiles.data['isIslandStart'].astext.cast(db.Boolean) == True
    ).first()

    if not starting_tile:
        logging.error(f"No starting tile found for chosen island {chosen_island_id} (Region: {chosen_region.name}).")
        return {"error": f"ConfigurationError: Starting tile for {chosen_region.name} not found. Contact admin."}

    logging.info(f"Team {team_id} selected island {chosen_region.name}, starting on tile {starting_tile.name}.")

    save.previousTile = None
    save.currentTile = starting_tile.id
    save.islandId = chosen_island_id
    
    # Only consume 1 movement from the roll, and keep isRolling true if we have remaining moves
    save.roll_state.roll_remaining = max(0, save.roll_state.roll_remaining - 1)  # Subtract 1 for landing on the first tile

    # Keep the team's dice since we're continuing the roll if we have moves left
    if save.roll_state.roll_remaining == 0:
        # Only set isRolling to False if we've used all our movement
        save.isRolling = False
        action_type = RollState.ACTION_TYPES["COMPLETE"]
        
        response_data = {
            "message": f"Welcome to {chosen_region.name}! You have started on tile '{starting_tile.name}'.",
            "current_tile": {"id": str(starting_tile.id), "name": starting_tile.name, "description": starting_tile.description or ""},
            "current_island": {"id": str(chosen_island_id), "name": chosen_region.name},
            "is_tile_completed": save.isTileCompleted,
            "coins": save.coins,
            "stars": save.stars,
            "action_required": action_type,
            "action_data": {
                "message": f"Landed on starting tile: {starting_tile.name}.",
                "current_tile": {"id": str(starting_tile.id), "name": starting_tile.name, "description": starting_tile.description or ""},
                "is_tile_completed_on_land": save.isTileCompleted
            }
        }
    else:
        # We have moves left, so continue the roll
        save.isRolling = True
        
        save.roll_state.current_tile_id = save.currentTile
        
        logging.info(f"Island selected with {save.roll_state.roll_remaining} moves remaining. Continuing movement without checking for special tile.")
        
        # During first island selection, we immediately process the next move without checking if it's a special tile
        return _process_next_move(event_id, team_id, save)
    
    return response_data

def _complete_roll(event_id, team_id, save: SaveData) -> dict:
    logging.info(f"Completing roll for team {team_id} on tile {save.currentTile}")
    
    current_tile_obj = SP3EventTiles.query.filter_by(id=save.currentTile).first()
    tile_info = {}

    if current_tile_obj:
        logging.debug(f"Final tile landed on: {current_tile_obj.name} (ID: {current_tile_obj.id})")
        tile_info = {
            "id": str(current_tile_obj.id), "name": current_tile_obj.name,
            "description": current_tile_obj.description or ""
        }
        challenge_mappings: list[SP3EventTileChallengeMapping] = SP3EventTileChallengeMapping.query.filter_by(tile_id=current_tile_obj.id).all()
        challenge_mappings_count = len(challenge_mappings)
        if challenge_mappings_count == 0:
            logging.info(f"Tile {current_tile_obj.name} has no challenges. Auto-marking as completed.")
            save.isTileCompleted = True
        else:
            logging.info(f"Tile {current_tile_obj.name} has {challenge_mappings_count} challenges. Completion depends on progress.")

            if current_tile_obj.data.get("category", "ANY") == "RANDOM":
                # Pick a random challenge to be the tile challenge
                save.currentChallenges = [random.choice(challenge_mappings).challenge_id]
                task_strings = []

                for challenge_id in save.currentChallenges:
                    challenge = EventChallenges.query.filter_by(id=challenge_id).first()
                    tasks = challenge.tasks
                    for task_id in tasks:
                        task = EventTasks.query.filter_by(id=task_id).first()
                        if task:
                            triggers = task.triggers
                            trigger_list = []
                            for trigger_id in triggers:
                                trigger = EventTriggers.query.filter_by(id=trigger_id).first()
                                if trigger.type == "DROP":
                                    trigger_list.append(f"{trigger.trigger}{" from " + trigger.source if trigger.source else ""}")
                                elif trigger.type == "KC":
                                    trigger_list.append(f"{trigger.trigger} KC")
                            triggers_message = " OR ".join(trigger_list)
                            
                            task_strings.append(f"{task.quantity}x {triggers_message}")

                tile_info["description"] = f"Random challenge selected:\n{'\n'.join(task_strings)}"
                logging.info(f"Random challenge selected for tile {current_tile_obj.name}: {save.currentChallenges}")        
    
            for challenge_map in challenge_mappings:
                challenge_id = challenge_map.challenge_id
                tasks = EventChallenges.query.filter_by(id=challenge_id).first().tasks
                if challenge_id not in save.tileProgress:
                    save.tileProgress[str(challenge_id)] = {}

                for task_id in tasks:
                    save.tileProgress[str(challenge_id)][str(task_id)] = 0 # Reset task progress for the challenge
    else:
        logging.warning(f"Final tile ID {save.currentTile} not found. Cannot determine challenges.")
        tile_info = {"id": str(save.currentTile), "name": "Unknown Tile (Not Found)"}
        save.isTileCompleted = True
        
    # Mark roll as complete and update SaveData
    save.isRolling = False
    # Clear dice (will be set based on rewards and buffs in future methods)
    save.dice = []
    save.modifier = 0
    
    if save.roll_state:
        # Reset roll state
        save.roll_state.roll_remaining = 0
        save.roll_state.action_required = RollState.ACTION_TYPES["COMPLETE"]
        
        # Add current tile to path if not already there
        if not save.roll_state.path_taken_this_turn or save.roll_state.path_taken_this_turn[-1] != save.currentTile:
            save.roll_state.path_taken_this_turn.append(save.currentTile)
            
        logging.info(f"Roll completed for team {team_id}. Final tile: {tile_info.get('name')}. isTileCompleted: {save.isTileCompleted}")

        save.roll_state.action_required = RollState.ACTION_TYPES["COMPLETE"]
        save.roll_state.action_data = {
            "message": "Roll completed. You've reached your destination!",
            "current_tile": tile_info,
            "dice_results_for_roll": save.roll_state.dice_results_for_roll,
            "modifier_for_roll": save.roll_state.modifier_for_roll,
            "roll_total_for_turn": save.roll_state.roll_total_for_turn,
            "path_taken_this_turn": [SP3EventTiles.query.filter(SP3EventTiles.id == tid).first().name for tid in save.roll_state.path_taken_this_turn],
            "is_tile_completed_on_land": save.isTileCompleted
        }
        return save.roll_state.to_dict()
    else:
        # No roll state, create a minimal completion response
        logging.warning(f"No roll state found for team {team_id} when completing roll")
        return {
            "action_required": RollState.ACTION_TYPES["COMPLETE"],
            "action_data": {
                "message": "Roll completed. You've reached your destination!",
                "current_tile": tile_info,
                "is_tile_completed_on_land": save.isTileCompleted
            }
        }
