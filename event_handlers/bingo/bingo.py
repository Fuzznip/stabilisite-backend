from datetime import datetime, timezone
from app import db
from event_handlers.event_handler import EventSubmission, NotificationResponse, NotificationAuthor
from models.models import Events, EventTeams, EventTeamMemberMappings, EventChallenges, EventTasks, EventTriggers, EventTriggerMappings, EventLog
from models.bingo import BingoTiles, BingoChallenges, BingoTeam, BingoTile, BingoTask
from helper.jsonb import update_jsonb_field

import logging
from sqlalchemy import func

def bingo_handler(submission: EventSubmission) -> list[NotificationResponse]:
    # Find most recent Bingo event
    now = datetime.now(timezone.utc)
    event: Events = Events.query.filter(
        Events.start_time <= now, 
        Events.end_time >= now, 
        Events.type == "BINGO"
    ).first()
    if event is None:
        logging.info("No active Bingo event found.")
        return []
    
    # Log the submission for the event
    event_log_entry: EventLog = EventLog(
        event_id=event.id,
        rsn=submission.rsn,
        discord_id=submission.id,
        trigger=submission.trigger,
        source=submission.source,
        quantity=submission.quantity,
        type=submission.type,
        value=submission.totalValue,
        timestamp=now
    )
    db.session.add(event_log_entry)
    db.session.commit()

    # Query the database to see if the user is in the event
    username = submission.rsn
    discord_id = submission.id
    player = EventTeamMemberMappings.query.join(EventTeams).filter(
        EventTeams.event_id == event.id,
        (
            func.lower(EventTeamMemberMappings.rsn) == username.lower()
        ) | (
            func.lower(EventTeamMemberMappings.discord_id) == str(discord_id).lower()
        )
    ).first()

    if player is None:
        logging.info(f"User {submission.rsn} (ID: {submission.id}) is not a participant in the Bingo event.")
        return []
    
    # Check to see if the submission matches any triggers for the event
    trigger = EventTriggerMappings.query.join(EventTasks).join(EventChallenges).filter(
        EventChallenges.event_id == event.id,
        EventTasks.id == trigger.task_id,
        EventChallenges.id == trigger.challenge_id,
        (EventTasks.type == "BINGO" ) & (EventTasks.status == "ACTIVE")
    ).first()

    if trigger is None:
        return []

    # Find the tile that this submission applies to
    # Grab all of the tasks that this trigger is referenced by
    tasks = EventTasks.query.filter(EventTasks.triggers.contains([trigger.id])).all()
    if not tasks:
        logging.error(f"No tasks found for trigger ID {trigger.id} in Bingo event {event.id}.\nSubmission: {submission}")
        return []
    
    # Grab all of the challenges for those tasks
    challenges = EventChallenges.query.filter(EventChallenges.id.in_([task.challenge_id for task in tasks])).all()
    if not challenges:
        logging.error(f"No challenges found for tasks {[task.id for task in tasks]} in Bingo event {event.id}.\nSubmission: {submission}")
        return []
    
    # Find the tasks that have those challenges
    tasks = BingoChallenges.query.filter(BingoChallenges.id.in_([challenge.id for challenge in challenges])).all()
    if not tasks:
        logging.error(f"No Bingo tasks found for challenges {[challenge.id for challenge in challenges]} in Bingo event {event.id}.\nSubmission: {submission}")
        return []
    
    # Find the tiles that have those tasks
    tiles = BingoTiles.query.filter(BingoTiles.id.in_([task.tile_id for task in tasks])).all()
    if not tiles:
        logging.error(f"No Bingo tiles found for tasks {[task.id for task in tasks]} in Bingo event {event.id}.\nSubmission: {submission}")
        return []
    
    # Update the team's board state
    team = EventTeams.query.filter_by(id=player.team_id).first()
    if team is None:
        logging.error(f"Team with ID {player.team_id} not found for player {player.rsn} in Bingo event {event.id}.\nSubmission: {submission}")
        return []
    
    team_data: BingoTeam = BingoTeam(**team.data)
    
    # # Iterate through the tasks and update progress
    # for tile in tiles:



    # save the team data back to the database
    team.data = team_data.__dict__
    db.session.commit()

    return [NotificationResponse(
        author=NotificationAuthor.SYSTEM,
        message="No active Bingo event found."
    )]
