from datetime import datetime, timezone
from app import db
from app import firestore_db
from event_handlers.event_handler import EventSubmission, NotificationField, NotificationResponse, NotificationAuthor
from models.models import Users
from models.new_events import (
    Event, Team, TeamMember, Action, Trigger, Tile, Task, Challenge,
    TileStatus, TaskStatus, ChallengeStatus, ChallengeProof
)

import logging
from sqlalchemy import func, text

def write_to_firestore(submission: EventSubmission, event: Event, action: Action, user: Users, team: Team | None = None):
    """Write submission to Firestore for backwards compatibility"""
    drop = {
        "id": str(action.id),
        "event_id": str(event.id),
        "rsn": submission.rsn,  # Original submitted RSN (may be alt name)
        "discord_id": submission.id,
        "trigger": submission.trigger,
        "source": submission.source,
        "quantity": submission.quantity,
        "type": submission.type,
        "value": submission.totalValue,
        "timestamp": action.date.isoformat() if action.date else None,
        "img_path": submission.img_path,
        # Resolved user info (the actual user, which may differ from submitted RSN if alt was used)
        "player_id": str(user.id),
        "player_rsn": user.runescape_name,
    }
    # Add team info if user is on a team
    if team:
        drop["team_id"] = str(team.id)
        drop["team_name"] = team.name
    try:
        if firestore_db:
            firestore_db.collection(f"drops_{event.id}").add(drop)
            logging.info(f"Wrote drop to Firestore for action: {action.id}")
    except Exception as e:
        logging.exception(f"Failed to write drop to Firestore for action: {action.id} : {e}")


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
                # For CHAT triggers, ignore source matching entirely (match on name only)
                source_matches = (trigger.type == "CHAT") or (not trigger_source_norm) or (trigger_source_norm == submission_source_norm)

                if trigger_name_match and source_matches:
                    # This submission matches this challenge! Update progress
                    task_completed = update_challenge_progress(
                        team, task, challenge, action, submission
                    )

                    if task_completed and tile.index not in completed_task_tile_indices:
                        completed_task_tile_indices.append(tile.index)

    return completed_task_tile_indices


def update_challenge_progress(team: Team, task: Task, challenge: Challenge, action: Action, submission: EventSubmission) -> bool:
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
        action_id=action.id,
        img_path=submission.img_path
    )
    db.session.add(proof)

    # Update quantity atomically to avoid race conditions under concurrent submissions
    effective_quantity = challenge.count_per_action if challenge.count_per_action is not None else submission.quantity
    db.session.execute(
        text("UPDATE new_stability.challenge_statuses SET quantity = quantity + :qty, updated_at = NOW() WHERE id = :cs_id"),
        {"qty": effective_quantity, "cs_id": str(challenge_status.id)}
    )
    db.session.flush()
    db.session.refresh(challenge_status)

    # Check if challenge is now complete
    # If quantity is NULL, challenge is repeatable and never completes
    if challenge.quantity is not None and challenge_status.quantity >= challenge.quantity and not challenge_status.completed:
        challenge_status.completed = True

        # If this challenge has a parent, update parent progress
        if challenge.parent_challenge_id:
            return update_parent_challenge_progress(team, task, challenge)
        else:
            # Check if this completes the task
            return check_and_update_task_completion(team, task)
    elif challenge.quantity is None and challenge.parent_challenge_id:
        # Repeatable challenge (quantity=NULL) with a parent
        # Update parent on every submission since this child never "completes"
        return update_parent_challenge_progress(team, task, challenge)

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

    # Sum the progress of all child challenges
    child_challenges = Challenge.query.filter_by(
        parent_challenge_id=parent_challenge.id
    ).all()

    total_children_value = 0
    for child in child_challenges:
        child_status = ChallengeStatus.query.filter_by(
            team_id=team.id,
            challenge_id=child.id
        ).first()

        if child_status:
            if child.quantity is None:
                # Repeatable child: multiply status quantity by child's value
                # Each submission counts as (child.value) points towards parent
                total_children_value += child_status.quantity * (child.value or 1)
            elif child_status.completed:
                # Completable child: add the child's value when completed
                total_children_value += (child.value or 1)

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

    # Update parent quantity to reflect sum of children progress
    parent_status.quantity = total_children_value

    # Check if parent challenge is now complete
    if total_children_value >= parent_challenge.quantity and not parent_status.completed:
        parent_status.completed = True
        db.session.commit()

        # Check if parent has a parent (grandparent structure)
        if parent_challenge.parent_challenge_id:
            # Recursively update grandparent
            return update_parent_challenge_progress(team, task, parent_challenge)
        else:
            # No grandparent, check if this completes the task
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

    # Look up user by runescape_name, alt_names, or discord_id
    user = None
    if submission.rsn:
        # First try exact match on runescape_name
        user = Users.query.filter(func.lower(Users.runescape_name) == submission.rsn.lower()).first()
        # If not found, check if the RSN is in any user's alt_names (case-insensitive)
        if not user:
            user = Users.query.filter(
                text("lower(:rsn) = ANY(SELECT lower(x) FROM unnest(alt_names) x)")
            ).params(rsn=submission.rsn).first()
    if not user and submission.id:
        user = Users.query.filter_by(discord_id=submission.id).first()

    if not user:
        logging.warning(f"User not found for submission: rsn={submission.rsn}, discord_id={submission.id}")
        return []

    # Check if user is a team member in this event (do this early so we can include in Firestore)
    team = None
    team_member = TeamMember.query.join(Team).filter(
        Team.event_id == event.id,
        TeamMember.user_id == user.id
    ).first()

    if team_member:
        team = Team.query.filter_by(id=team_member.team_id).first()

    # Create Action object (new event system)
    action = Action(
        player_id=user.id,
        type=submission.type,
        name=submission.trigger,
        source=submission.source,
        quantity=submission.quantity,
        value=submission.totalValue,
        date=datetime.now(timezone.utc)
    )
    db.session.add(action)
    db.session.commit()

    # Write to Firestore (backwards compatibility) - includes user and team info
    write_to_firestore(submission, event, action, user, team)

    # If user is not on a team, we've already logged to Firestore, just return
    if not team_member or not team:
        logging.info(f"User {submission.rsn} (ID: {submission.id}) is not a participant in the Bingo event.")
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
