from datetime import datetime, timezone
from app import db
from app import firestore_db
from event_handlers.event_handler import EventSubmission, NotificationField, NotificationResponse, NotificationAuthor
from models.models import Events, EventTeams, EventTeamMemberMappings, EventChallenges, EventTasks, EventTriggers, EventTriggerMappings, EventLog
from models.bingo import BingoTileProgress, BingoTaskProgress, BingoTriggerProgress, BingoTiles, BingoChallenges, BingoTeam, BingoTile, BingoTask
from helper.jsonb import update_jsonb_field

import logging
from sqlalchemy import func

class BingoProgress:
    is_task_completed: bool = False
    progressed_task_tile_index: int = -1
    progressed_task_id: str = ""
    new_progress: BingoTileProgress | None = None

def progress_tile(submission: EventSubmission, tile_progress: BingoTileProgress, tile: BingoTiles, team_data: BingoTeam) -> BingoProgress | None:
    bingo_progress = BingoProgress()
    bingo_progress.new_progress = tile_progress

    # Grab the tasks (bingo challenges) for this tile
    tasks: list[BingoChallenges] = BingoChallenges.query.filter_by(tile_id=tile.id).all()
    if not tasks or len(tasks) == 0:
        logging.error(f"No tasks found for tile {tile.id}.")
        return None

    # Check each bingo challenge to see if the submission progresses it
    for task in tasks:
        bingo_task_id: str = task.id
        for challenge_id in task.challenges:
            # Get the event challenge
            event_challenge: EventChallenges = EventChallenges.query.filter_by(id=challenge_id).first()
            if event_challenge is None:
                logging.error(f"Event challenge {challenge_id} not found for bingo task {bingo_task_id}.")
                continue

            # Attempt to progress the challenge with the submission
            # Loop through the tasks in the event challenge
            for task_id in event_challenge.tasks:
                event_task: EventTasks = EventTasks.query.filter_by(id=task_id).first()

                for task_trigger_id in event_task.triggers:
                    # Check if the submission's trigger matches the event trigger
                    event_trigger: EventTriggers = EventTriggers.query.filter_by(id=task_trigger_id).first()

                    # Normalize source for comparison
                    trigger_source_norm = event_trigger.source.lower() if event_trigger.source else ""
                    submission_source_norm = submission.source.lower() if submission.source else ""
                    
                    # If trigger source is empty, it can match any submission source (wildcard)
                    # OR if trigger source is specified, it must match submission source
                    source_matches = (not trigger_source_norm) or (trigger_source_norm == submission_source_norm)

                    if event_trigger.trigger.lower() == submission.trigger.lower() and source_matches:
                        # Progress the task
                        # Find the corresponding task progress in the tile progress
                        bingo_progress.progressed_task_id = bingo_task_id
                        bingo_progress.progressed_task_tile_index = tile.index
                        
                        task_completed = bingo_progress.new_progress.add_task_progress(bingo_task_id, task.task_index, event_challenge, event_task, submission.trigger, submission.quantity, event_challenge.type)
                        if task_completed:
                            # Award points for completing the task
                            
                            team_data.points += 3
                            team_data.board_state[tile.index] += 1

                            bingo_progress.is_task_completed = True
                        break  # No need to check other triggers for this event task
    
    return bingo_progress

# Process a submission for a team. Returns a list of completed tile indices
def progress_team(event: Events, submission: EventSubmission, team_data: BingoTeam) -> list[int]:
    # Grab all of the bingo tiles
    tiles: list[BingoTiles] = BingoTiles.query.filter_by(event_id=event.id).all()
    if not tiles or len(tiles) == 0:
        logging.error(f"No bingo tiles found for event {event.id}.")
        return []

    completed_task_tile_indices: set[int] = set()

    # Loop through each tile
    for tile in tiles:
        tile_index = tile.index
        # Check if the team already has progress for this tile
        tile_progress: BingoTileProgress | None = team_data.get_tile_progress(tile_index)
        if tile_progress is None:
            tile_progress = BingoTileProgress()
            tile_progress.tile_id = tile_index
            tile_progress.name = tile.name
            tile_progress.progress = []
            team_data.board_progress.append(tile_progress)

        # Attempt to progress the tile
        bingo_progress = progress_tile(submission, tile_progress, tile, team_data)
        # print values of bingo_progress
        if bingo_progress is None or bingo_progress.new_progress is None:
            continue
        
        team_data.update_tile_progress(bingo_progress.new_progress)
        # If any task was completed in this tile, add the tile index to the set
        if bingo_progress.is_task_completed:
            completed_task_tile_indices.add(tile_index)

    return list(completed_task_tile_indices)

def write_to_firestore(event_log: EventLog):
    try:
        firestore_db.collection("drops").add(event_log.to_dict())
        logging.info(f"Wrote drop to Firestore for event: ${event_log.id}")
    except Exception as e:
        logging.exception(f"Failed to write drop to Firestore for event: ${event_log.id} : {e}")

def check_row_for_bingo(tile_index: int, team_data: BingoTeam) -> bool:
    # Count the number of completed tasks in the tile index
    tile_progress = team_data.get_tile_progress(str(tile_index))
    completed_tasks = tile_progress.get_completed_task_count() if tile_progress else 0
    # Find the minimum number of completed tasks in the row
    row = tile_index // 5
    min_completed = 3  # Start with max possible (3 tasks per tile)
    for i in range(5):
        tile_progress = team_data.get_tile_progress(str(row * 5 + i))
        min_completed = min(min_completed, tile_progress.get_completed_task_count() if tile_progress else 0)
    return min_completed == completed_tasks

def check_column_for_bingo(tile_index: int, team_data: BingoTeam) -> bool:
    # Count the number of completed tasks in the tile index
    tile_progress = team_data.get_tile_progress(str(tile_index))
    completed_tasks = tile_progress.get_completed_task_count() if tile_progress else 0
    # Find the minimum number of completed tasks in the column
    col = tile_index % 5
    min_completed = 3  # Start with max possible (3 tasks per tile)
    for i in range(5):
        tile_progress = team_data.get_tile_progress(str(i * 5 + col))
        min_completed = min(min_completed, tile_progress.get_completed_task_count() if tile_progress else 0)
    return min_completed == completed_tasks

def bingo_handler(submission: EventSubmission) -> list[NotificationResponse]:
    # Find most recent Bingo event
    now: datetime = datetime.now(timezone.utc)
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
        value=submission.totalValue
    )
    db.session.add(event_log_entry)
    db.session.commit()
    
    write_to_firestore(event_log_entry)

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
    
    team: EventTeams = EventTeams.query.filter_by(id=player.team_id).first()
    if team is None:
        logging.error(f"Team with ID {player.team_id} not found for player {player.rsn} in Bingo event {event.id}.\nSubmission: {submission}")
        return []
    
    team_data: BingoTeam = BingoTeam.from_dict(team.data)

    # Progress the team based on the submission
    completed_task_tile_indices = progress_team(event, submission, team_data)
    
    # If no tasks were completed, return early
    if not completed_task_tile_indices or len(completed_task_tile_indices) == 0:
        # save the team data back to the database
        team.data = team_data.to_dict()
        db.session.commit()
        return []

    bingo_count = 0
    # If tasks were completed, check for bonus points for completing rows/columns
    for index in completed_task_tile_indices:
        if check_row_for_bingo(index, team_data):
            bingo_count += 1
        if check_column_for_bingo(index, team_data):
            bingo_count += 1

    # Award points for bingos
    team_data.points += bingo_count * 15

    # save the team data back to the database
    team.data = team_data.to_dict()
    db.session.commit()

    # Construct notification response based on completed tasks and bingos
    if bingo_count < 1:
        # Get the first tile that was completed
        first_completed_tile = completed_task_tile_indices[0] if completed_task_tile_indices else 0
        tile: BingoTiles = BingoTiles.query.filter_by(event_id=event.id, index=first_completed_tile).first()
        if tile is None:
            logging.error(f"Tile with index {first_completed_tile} not found for Bingo event {event.id}.")
            return []
        response: NotificationResponse = NotificationResponse(
            threadId=event.thread_id,
            title=f"{tile.name} Task Completed!",
            color=0xFFD700,  # Gold color
            description=f"The **{team_data.name}** have completed a task!",
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image
            ),
            fields=[
                NotificationField(
                    name="Total Points",
                    value=str(team_data.points),
                    inline=True
                )
            ]
        )
        return [response]
    elif bingo_count == 1:
        response: NotificationResponse = NotificationResponse(
            threadId=event.thread_id,
            title="Bingo!",
            color=0x00FF00,  # Green color
            description=f"The **{team_data.name}** have completed a row or column and scored a Bingo!",
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image
            ),
            fields=[
                NotificationField(
                    name="Total Points",
                    value=str(team_data.points),
                    inline=True
                )
            ]
        )
        return [response]
    elif bingo_count == 2:
        response: NotificationResponse = NotificationResponse(
            threadId=event.thread_id,
            title="Multiple Bingos!",
            color=0xFF4500,  # OrangeRed color
            description=f"The **{team_data.name}** have completed a double bingo!",
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image
            ),
            fields=[
                NotificationField(
                    name="Total Points",
                    value=str(team_data.points),
                    inline=True
                )
            ]
        )
        return [response]
    else: # This should technically not be possible and we'll have a funny message for it
        response: NotificationResponse = NotificationResponse(
            threadId=event.thread_id,
            title="Bingo Anomaly Detected!",
            color=0xFF0000,  # Red color
            description=f"The **{team.name}** have triggered an unexpected bingo count of {bingo_count}. Please contact an admin.",
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image
            ),
            fields=[
                NotificationField(
                    name="Total Points",
                    value=str(team_data.points),
                    inline=True
                )
            ]
        )

    return [NotificationResponse(
        threadId=event.thread_id,
        description="An unexpected error occurred while processing the bingo. Please contact an admin.",
        author=NotificationAuthor(
            name="Bingo Event",
            icon_url="https://i.imgur.com/3ZQ3Z3Q.png"
        ),
        title="This message should never be seen. @funzip"
    )]
    