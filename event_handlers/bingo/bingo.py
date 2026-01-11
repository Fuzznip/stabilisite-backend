from datetime import datetime, timezone
from app import db
from app import firestore_db
from event_handlers.event_handler import EventSubmission, NotificationField, NotificationResponse, NotificationAuthor
from models.models import Users, EventLog
from models.new_events import (
    Event, Team, TeamMember, Action, Trigger, Tile, Task, Challenge,
    TileStatus, TaskStatus, ChallengeStatus, ChallengeProof
)

import logging
from sqlalchemy import func

def write_to_firestore(event_log: EventLog):
    """Write event log to Firestore for backwards compatibility"""
    try:
        if firestore_db:
            firestore_db.collection("drops").add(event_log.to_dict())
            logging.info(f"Wrote drop to Firestore for event: {event_log.id}")
    except Exception as e:
        logging.exception(f"Failed to write drop to Firestore for event: {event_log.id} : {e}")


def process_submission_for_team(event: Event, submission: EventSubmission, team: Team, action: Action) -> list[int]:
    """
    Process a submission for a team and return list of tile indices where tasks were completed.

    This function:
    1. Finds all tiles for the event
    2. For each tile, checks all tasks
    3. For each task, checks all challenges
    4. If a challenge matches the submission, updates progress
    5. Returns list of tile indices where tasks were completed
    """
    completed_task_tile_indices = []

    # Get all tiles for this event
    tiles = Tile.query.filter_by(event_id=event.id).all()
    if not tiles:
        logging.error(f"No tiles found for event {event.id}")
        return []

    for tile in tiles:
        # Get all tasks for this tile
        tasks = Task.query.filter_by(tile_id=tile.id).all()
        if not tasks:
            continue

        for task in tasks:
            # Get all challenges for this task
            challenges = Challenge.query.filter_by(task_id=task.id).all()
            if not challenges:
                continue

            for challenge in challenges:
                # Skip parent challenges (no trigger)
                if not challenge.trigger_id:
                    continue

                # Get the trigger for this challenge
                trigger = Trigger.query.filter_by(id=challenge.trigger_id).first()
                if not trigger:
                    continue

                # Check if submission matches this trigger
                trigger_name_match = trigger.name.lower() == submission.trigger.lower()

                # Normalize source for comparison
                trigger_source_norm = trigger.source.lower() if trigger.source else ""
                submission_source_norm = submission.source.lower() if submission.source else ""

                # If trigger source is empty, it can match any submission source (wildcard)
                # OR if trigger source is specified, it must match submission source
                source_matches = (not trigger_source_norm) or (trigger_source_norm == submission_source_norm)

                if trigger_name_match and source_matches:
                    # This submission matches this challenge! Update progress
                    task_completed = update_challenge_progress(
                        team, task, challenge, action, submission.quantity
                    )

                    if task_completed and tile.index not in completed_task_tile_indices:
                        completed_task_tile_indices.append(tile.index)

    return completed_task_tile_indices


def update_challenge_progress(team: Team, task: Task, challenge: Challenge, action: Action, quantity: int) -> bool:
    """
    Update progress for a challenge and return True if the task was completed as a result.

    Returns:
        bool: True if this update caused the task to be completed, False otherwise
    """
    # Get or create challenge status
    challenge_status = ChallengeStatus.query.filter_by(
        team_id=team.id,
        challenge_id=challenge.id
    ).first()

    if not challenge_status:
        challenge_status = ChallengeStatus(
            team_id=team.id,
            challenge_id=challenge.id,
            quantity=0,
            completed=False
        )
        db.session.add(challenge_status)
        db.session.flush()  # Flush to get the ID for the proof

    # Add proof (link to action)
    proof = ChallengeProof(
        challenge_status_id=challenge_status.id,
        action_id=action.id
    )
    db.session.add(proof)

    # Update quantity
    challenge_status.quantity += quantity

    # Check if challenge is now complete
    if challenge_status.quantity >= challenge.quantity and not challenge_status.completed:
        challenge_status.completed = True

        # If this challenge has a parent, update parent progress
        if challenge.parent_challenge_id:
            return update_parent_challenge_progress(team, task, challenge)
        else:
            # Check if this completes the task
            return check_and_update_task_completion(team, task)

    db.session.commit()
    return False


def update_parent_challenge_progress(team: Team, task: Task, child_challenge: Challenge) -> bool:
    """
    Update parent challenge progress when a child challenge is completed.

    Returns:
        bool: True if this caused the task to be completed, False otherwise
    """
    parent_challenge = Challenge.query.get(child_challenge.parent_challenge_id)
    if not parent_challenge:
        return False

    # Count how many child challenges are completed
    child_challenges = Challenge.query.filter_by(
        parent_challenge_id=parent_challenge.id
    ).all()

    completed_children = 0
    for child in child_challenges:
        child_status = ChallengeStatus.query.filter_by(
            team_id=team.id,
            challenge_id=child.id,
            completed=True
        ).first()
        if child_status:
            completed_children += 1

    # Get or create parent challenge status
    parent_status = ChallengeStatus.query.filter_by(
        team_id=team.id,
        challenge_id=parent_challenge.id
    ).first()

    if not parent_status:
        parent_status = ChallengeStatus(
            team_id=team.id,
            challenge_id=parent_challenge.id,
            quantity=0,
            completed=False
        )
        db.session.add(parent_status)
        db.session.flush()

    # Update parent quantity to reflect number of children completed
    parent_status.quantity = completed_children

    # Check if parent challenge is now complete
    if completed_children >= parent_challenge.quantity and not parent_status.completed:
        parent_status.completed = True
        db.session.commit()
        # Check if this completes the task
        return check_and_update_task_completion(team, task)

    db.session.commit()
    return False


def check_and_update_task_completion(team: Team, task: Task) -> bool:
    """
    Check if all required challenges for a task are complete and update task status.

    Returns:
        bool: True if the task was completed as a result of this check, False otherwise
    """
    # Get task status
    task_status = TaskStatus.query.filter_by(
        team_id=team.id,
        task_id=task.id
    ).first()

    if not task_status:
        task_status = TaskStatus(
            team_id=team.id,
            task_id=task.id,
            completed=False
        )
        db.session.add(task_status)

    # If already completed, return False
    if task_status.completed:
        return False

    # Get all TOP-LEVEL challenges for this task (exclude children of parent challenges)
    all_challenges = Challenge.query.filter_by(task_id=task.id).all()
    challenges = [c for c in all_challenges if c.parent_challenge_id is None]

    # Check if all challenges are complete
    if task.require_all:
        # AND logic: all top-level challenges must be complete
        all_complete = True
        for challenge in challenges:
            challenge_status = ChallengeStatus.query.filter_by(
                team_id=team.id,
                challenge_id=challenge.id
            ).first()
            if not challenge_status or not challenge_status.completed:
                all_complete = False
                break

        if all_complete:
            task_status.completed = True
            update_tile_status(team, task.tile_id)
            db.session.commit()
            return True
    else:
        # OR logic: any top-level challenge can complete the task
        for challenge in challenges:
            challenge_status = ChallengeStatus.query.filter_by(
                team_id=team.id,
                challenge_id=challenge.id
            ).first()
            if challenge_status and challenge_status.completed:
                task_status.completed = True
                update_tile_status(team, task.tile_id)
                db.session.commit()
                return True

    db.session.commit()
    return False


def update_tile_status(team: Team, tile_id: str):
    """Update tile status based on completed tasks"""
    # Get or create tile status
    tile_status = TileStatus.query.filter_by(
        team_id=team.id,
        tile_id=tile_id
    ).first()

    if not tile_status:
        tile_status = TileStatus(
            team_id=team.id,
            tile_id=tile_id,
            tasks_completed=0
        )
        db.session.add(tile_status)

    # Count completed tasks for this tile
    tasks = Task.query.filter_by(tile_id=tile_id).all()
    completed_count = 0

    for task in tasks:
        task_status = TaskStatus.query.filter_by(
            team_id=team.id,
            task_id=task.id
        ).first()
        if task_status and task_status.completed:
            completed_count += 1

    # Update tile status (cap at 3)
    tile_status.tasks_completed = min(completed_count, 3)

    # Award 3 points per task completed
    team.points += 3

    db.session.commit()


def check_row_for_bingo(tile_index: int, team: Team, event: Event) -> bool:
    """Check if a row has achieved bingo (all tiles have same number of completed tasks)"""
    # Get the tile at this index to determine completion level
    tile = Tile.query.filter_by(event_id=event.id, index=tile_index).first()
    if not tile:
        return False

    tile_status = TileStatus.query.filter_by(team_id=team.id, tile_id=tile.id).first()
    if not tile_status:
        return False

    completed_tasks = tile_status.tasks_completed
    if completed_tasks == 0:
        return False

    # Find the minimum number of completed tasks in the row
    row = tile_index // 5
    min_completed = completed_tasks

    for i in range(5):
        row_tile_index = row * 5 + i
        row_tile = Tile.query.filter_by(event_id=event.id, index=row_tile_index).first()
        if row_tile:
            row_tile_status = TileStatus.query.filter_by(team_id=team.id, tile_id=row_tile.id).first()
            tile_completed = row_tile_status.tasks_completed if row_tile_status else 0
            min_completed = min(min_completed, tile_completed)

    return min_completed == completed_tasks


def check_column_for_bingo(tile_index: int, team: Team, event: Event) -> bool:
    """Check if a column has achieved bingo (all tiles have same number of completed tasks)"""
    # Get the tile at this index to determine completion level
    tile = Tile.query.filter_by(event_id=event.id, index=tile_index).first()
    if not tile:
        return False

    tile_status = TileStatus.query.filter_by(team_id=team.id, tile_id=tile.id).first()
    if not tile_status:
        return False

    completed_tasks = tile_status.tasks_completed
    if completed_tasks == 0:
        return False

    # Find the minimum number of completed tasks in the column
    col = tile_index % 5
    min_completed = completed_tasks

    for i in range(5):
        col_tile_index = i * 5 + col
        col_tile = Tile.query.filter_by(event_id=event.id, index=col_tile_index).first()
        if col_tile:
            col_tile_status = TileStatus.query.filter_by(team_id=team.id, tile_id=col_tile.id).first()
            tile_completed = col_tile_status.tasks_completed if col_tile_status else 0
            min_completed = min(min_completed, tile_completed)

    return min_completed == completed_tasks


def bingo_handler(submission: EventSubmission) -> list[NotificationResponse]:
    """Main handler for bingo event submissions"""
    # Find active bingo event
    now = datetime.now(timezone.utc)
    event = Event.query.filter(
        Event.start_date <= now,
        Event.end_date >= now
    ).first()

    if not event:
        logging.info("No active Bingo event found.")
        return []

    # Look up user by runescape_name or discord_id
    user = None
    if submission.rsn:
        user = Users.query.filter(func.lower(Users.runescape_name) == submission.rsn.lower()).first()
    if not user and submission.id:
        user = Users.query.filter_by(discord_id=submission.id).first()

    if not user:
        logging.warning(f"User not found for submission: rsn={submission.rsn}, discord_id={submission.id}")
        return []

    # Create Action object (new event system)
    action = Action(
        player_id=user.id,
        type=submission.type,
        name=submission.trigger,
        source=submission.source,
        quantity=submission.quantity,
        value=submission.totalValue
    )
    db.session.add(action)
    db.session.commit()

    # Write to Firestore (backwards compatibility)
    if event:
        temp_event_log = EventLog(
            event_id=str(event.id),
            rsn=submission.rsn,
            discord_id=submission.id,
            trigger=submission.trigger,
            source=submission.source,
            quantity=submission.quantity,
            type=submission.type,
            value=submission.totalValue
        )
        write_to_firestore(temp_event_log)

    # Check if user is a team member in this event
    team_member = TeamMember.query.join(Team).filter(
        Team.event_id == event.id,
        TeamMember.user_id == user.id
    ).first()

    if not team_member:
        logging.info(f"User {submission.rsn} (ID: {submission.id}) is not a participant in the Bingo event.")
        return []

    team = Team.query.filter_by(id=team_member.team_id).first()
    if not team:
        logging.error(f"Team with ID {team_member.team_id} not found for user {user.id} in Bingo event {event.id}.")
        return []

    # Process the submission for this team
    completed_task_tile_indices = process_submission_for_team(event, submission, team, action)

    # If no tasks were completed, return early
    if not completed_task_tile_indices:
        return []

    # Check for bingos (completed rows/columns)
    bingo_count = 0
    for index in completed_task_tile_indices:
        if check_row_for_bingo(index, team, event):
            bingo_count += 1
        if check_column_for_bingo(index, team, event):
            bingo_count += 1

    # Award bonus points for bingos
    if bingo_count > 0:
        team.points += bingo_count * 15
        db.session.commit()

    # Construct notification response
    if bingo_count < 1:
        # Get the first tile that was completed
        first_completed_tile_index = completed_task_tile_indices[0]
        tile = Tile.query.filter_by(event_id=event.id, index=first_completed_tile_index).first()
        if not tile:
            logging.error(f"Tile with index {first_completed_tile_index} not found for Bingo event {event.id}.")
            return []

        response = NotificationResponse(
            threadId=event.thread_id,
            title=f"{tile.name} Task Completed!",
            color=0xFFD700,  # Gold color
            description=f"The **{team.name}** have completed a task!",
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image_url
            ),
            fields=[
                NotificationField(
                    name="Total Points",
                    value=str(team.points),
                    inline=True
                )
            ]
        )
        return [response]

    elif bingo_count == 1:
        response = NotificationResponse(
            threadId=event.thread_id,
            title="Bingo!",
            color=0x00FF00,  # Green color
            description=f"The **{team.name}** have completed a row or column and scored a Bingo!",
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image_url
            ),
            fields=[
                NotificationField(
                    name="Total Points",
                    value=str(team.points),
                    inline=True
                )
            ]
        )
        return [response]

    elif bingo_count == 2:
        response = NotificationResponse(
            threadId=event.thread_id,
            title="Multiple Bingos!",
            color=0xFF4500,  # OrangeRed color
            description=f"The **{team.name}** have completed a double bingo!",
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image_url
            ),
            fields=[
                NotificationField(
                    name="Total Points",
                    value=str(team.points),
                    inline=True
                )
            ]
        )
        return [response]

    else:
        # This should technically not be possible
        response = NotificationResponse(
            threadId=event.thread_id,
            title="Bingo Anomaly Detected!",
            color=0xFF0000,  # Red color
            description=f"The **{team.name}** have triggered an unexpected bingo count of {bingo_count}. Please contact an admin.",
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image_url
            ),
            fields=[
                NotificationField(
                    name="Total Points",
                    value=str(team.points),
                    inline=True
                )
            ]
        )
        return [response]
