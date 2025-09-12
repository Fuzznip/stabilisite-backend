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
            func.lower(EventTeamMemberMappings.username) == username.lower()
        ) | (
            func.lower(EventTeamMemberMappings.discord_id) == str(discord_id).lower()
        )
    ).first()

    if player is None:
        logging.info(f"User {submission.rsn} (ID: {submission.id}) is not a participant in the Bingo event.")
        return []
    
    team = EventTeams.query.filter_by(id=player.team_id).first()
    if team is None:
        logging.error(f"Team with ID {player.team_id} not found for player {player.rsn} in Bingo event {event.id}.\nSubmission: {submission}")
        return []
    
    team_data: BingoTeam = BingoTeam()
    for key, value in team.data.items():
        setattr(team_data, key, value)

    # ensure default values for missing fields
    if not hasattr(team_data, 'points'):
        team_data.points = 0
    if not hasattr(team_data, 'board_state'):
        team_data.board_state = [0] * 25  # Assuming a 5x5 board
    if not hasattr(team_data, 'board_progress'):
        team_data.board_progress = []
    if not hasattr(team_data, 'members'):
        team_data.members = []
    if not hasattr(team_data, 'image_url'):
        team_data.image_url = ""
    if not hasattr(team_data, 'name'):
        team_data.name = "Unnamed Team"
    if not hasattr(team_data, 'team_id'):
        team_data.team_id = str(team.id)
    
    # # Get all tiles for the event
    # tiles = BingoTiles.query.filter_by(event_id=event.id).all()
    # for tile in tiles:
    #     # Check all challenges for the tile
    #     tile_challenges = BingoChallenges.query.filter_by(tile_id=tile.id).all()
    #     for tile_challenge in tile_challenges:
    #         # If the challenge is not already in the team data, add it
    #         if tile_challenge.id not in team_data.challenges:
    #             team_data.challenges[tile_challenge.id] = tile_challenge.challenges

    # save the team data back to the database
    team.data = team_data.__dict__
    db.session.commit()

    return []

    return [NotificationResponse(
        author="stability itself",
        title="This message should never be seen. @funzip"
    )]
