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
import threading
from sqlalchemy import func, text
from sqlalchemy.orm import joinedload


def write_to_firestore(submission: EventSubmission, event: Event, action: Action, user: Users, team: Team | None = None):
    """Write submission to Firestore for backwards compatibility (fire-and-forget)"""
    # Build the drop dict on the calling thread while SQLAlchemy objects are still valid
    drop = {
        "id": str(action.id),
        "event_id": str(event.id),
        "rsn": submission.rsn,
        "discord_id": submission.id,
        "trigger": submission.trigger,
        "source": submission.source,
        "quantity": submission.quantity,
        "type": submission.type,
        "value": submission.totalValue,
        "timestamp": action.date.isoformat() if action.date else None,
        "img_path": submission.img_path,
        "player_id": str(user.id),
        "player_rsn": user.runescape_name,
    }
    if team:
        drop["team_id"] = str(team.id)
        drop["team_name"] = team.name

    collection_name = f"drops_{event.id}"

    def _write():
        try:
            if firestore_db:
                firestore_db.collection(collection_name).add(drop)
                logging.info(f"Wrote drop to Firestore for action: {drop['id']}")
        except Exception as e:
            logging.exception(f"Failed to write drop to Firestore for action: {drop['id']} : {e}")

    threading.Thread(target=_write, daemon=True).start()


def process_submission_for_team(event: Event, submission: EventSubmission, team: Team, action: Action) -> list[int]:
    """
    Process a submission for a team and return list of tile indices where tasks were completed.

    Batch-loads all tiles, tasks, challenges, and triggers for the event upfront
    to avoid N+1 query patterns.
    """
    completed_task_tile_indices = []

    # Batch load all data for this event in 4 queries
    tiles = Tile.query.filter_by(event_id=event.id).all()
    if not tiles:
        logging.error(f"No tiles found for event {event.id}")
        return []

    tile_ids = [t.id for t in tiles]
    all_tasks = Task.query.filter(Task.tile_id.in_(tile_ids)).all()
    task_ids = [t.id for t in all_tasks]
    all_challenges = Challenge.query.filter(Challenge.task_id.in_(task_ids)).all() if task_ids else []

    trigger_ids = list(set(c.trigger_id for c in all_challenges if c.trigger_id))
    all_triggers = Trigger.query.filter(Trigger.id.in_(trigger_ids)).all() if trigger_ids else []

    # Build lookup dicts
    triggers_by_id = {t.id: t for t in all_triggers}
    tasks_by_tile = {}
    for task in all_tasks:
        tasks_by_tile.setdefault(task.tile_id, []).append(task)
    challenges_by_task = {}
    for challenge in all_challenges:
        challenges_by_task.setdefault(challenge.task_id, []).append(challenge)

    # Pre-normalize submission values
    submission_trigger_lower = submission.trigger.lower()
    submission_source_lower = submission.source.lower() if submission.source else ""

    for tile in tiles:
        for task in tasks_by_tile.get(tile.id, []):
            for challenge in challenges_by_task.get(task.id, []):
                if not challenge.trigger_id:
                    continue

                trigger = triggers_by_id.get(challenge.trigger_id)
                if not trigger:
                    continue

                trigger_name_match = trigger.name.lower() == submission_trigger_lower
                trigger_source_norm = trigger.source.lower() if trigger.source else ""
                source_matches = (trigger.type == "CHAT") or (not trigger_source_norm) or (trigger_source_norm == submission_source_lower)

                if trigger_name_match and source_matches:
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

    # Batch load all child challenges and their statuses
    child_challenges = Challenge.query.filter_by(
        parent_challenge_id=parent_challenge.id
    ).all()

    child_ids = [c.id for c in child_challenges]
    child_statuses = ChallengeStatus.query.filter(
        ChallengeStatus.team_id == team.id,
        ChallengeStatus.challenge_id.in_(child_ids)
    ).all() if child_ids else []
    status_by_challenge = {s.challenge_id: s for s in child_statuses}

    total_children_value = 0
    for child in child_challenges:
        child_status = status_by_challenge.get(child.id)

        if child_status:
            if child.quantity is None:
                # Repeatable child: multiply status quantity by child's value
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

    # Batch load all challenge statuses in one query
    challenge_ids = [c.id for c in challenges]
    statuses = ChallengeStatus.query.filter(
        ChallengeStatus.team_id == team.id,
        ChallengeStatus.challenge_id.in_(challenge_ids)
    ).all() if challenge_ids else []
    status_by_id = {s.challenge_id: s for s in statuses}

    # Check if challenges are complete
    if task.require_all:
        # AND logic: all top-level challenges must be complete
        all_complete = all(
            (s := status_by_id.get(c.id)) and s.completed
            for c in challenges
        )

        if all_complete:
            task_status.completed = True
            update_tile_status(team, task.tile_id)
            db.session.commit()
            return True
    else:
        # OR logic: any top-level challenge can complete the task
        for challenge in challenges:
            s = status_by_id.get(challenge.id)
            if s and s.completed:
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

    # Batch count completed tasks in one query instead of N+1
    task_ids = [t.id for t in Task.query.filter_by(tile_id=tile_id).all()]
    completed_count = TaskStatus.query.filter(
        TaskStatus.team_id == team.id,
        TaskStatus.task_id.in_(task_ids),
        TaskStatus.completed == True
    ).count() if task_ids else 0

    # Update tile status (cap at 3)
    tile_status.tasks_completed = min(completed_count, 3)

    # Award 3 points using atomic SQL UPDATE to prevent race conditions
    db.session.flush()
    db.session.execute(
        text("UPDATE new_stability.teams SET points = points + 3, updated_at = NOW() WHERE id = :team_id"),
        {"team_id": str(team.id)}
    )

    db.session.commit()


def check_bingos_for_completed_tiles(completed_tile_indices: list[int], team: Team, event: Event) -> int:
    """
    Check for new bingos caused by the completed tiles.
    Uses a single batch query with joinedload instead of per-cell queries.

    Returns:
        Number of new bingos detected
    """
    tile_statuses = TileStatus.query.join(Tile).options(
        joinedload(TileStatus.tile)
    ).filter(
        Tile.event_id == event.id,
        TileStatus.team_id == team.id
    ).all()

    # Build 5x5 grid of completion levels
    grid = [[0] * 5 for _ in range(5)]
    for ts in tile_statuses:
        if ts.tile:
            row, col = ts.tile.index // 5, ts.tile.index % 5
            grid[row][col] = ts.tasks_completed

    bingo_count = 0
    for idx in completed_tile_indices:
        row, col = idx // 5, idx % 5
        completed_tasks = grid[row][col]
        if completed_tasks == 0:
            continue

        # Check row: did this tile completing create a row bingo at this level?
        if min(grid[row]) == completed_tasks:
            bingo_count += 1

        # Check column: did this tile completing create a column bingo at this level?
        if min(grid[r][col] for r in range(5)) == completed_tasks:
            bingo_count += 1

    return bingo_count


def bingo_handler(submission: EventSubmission) -> list[NotificationResponse]:
    """Main handler for bingo event submissions"""
    logging.info(f"[BINGO] Received submission: rsn={submission.rsn}, discord_id={submission.id}, trigger={submission.trigger!r}, source={submission.source!r}, type={submission.type}, quantity={submission.quantity}")

    # Find active bingo event
    now = datetime.now(timezone.utc)
    event = Event.query.filter(
        Event.start_date <= now,
        Event.end_date >= now
    ).first()

    if not event:
        logging.info("No active Bingo event found.")
        return []

    # Look up user by runescape_name, discord_id, then alt_names (cheapest to most expensive)
    user = None
    if submission.rsn:
        # Normalize due to WoM changing underscores to spaces in RSN
        normalized_rsn = submission.rsn.replace("_", " ")
        # First try exact match on runescape_name (normalize underscores/spaces on both sides)
        user = Users.query.filter(
            func.lower(func.replace(Users.runescape_name, "_", " ")) == normalized_rsn.lower()
        ).first()
    # Try discord_id before alt_names (indexed lookup vs full table scan)
    if not user and submission.id:
        user = Users.query.filter_by(discord_id=submission.id).first()
    # Alt_names uses unnest (full table scan) — only as last resort
    if not user and submission.rsn:
        user = Users.query.filter(
            text("lower(replace(:rsn, '_', ' ')) = ANY(SELECT lower(replace(x, '_', ' ')) FROM unnest(alt_names) x)")
        ).params(rsn=submission.rsn).first()

    if not user:
        logging.warning(f"User not found for submission: rsn={submission.rsn}, discord_id={submission.id}")
        return []

    # Idempotency check: if a request_id is provided, reject if already processed
    if submission.request_id:
        existing_action = Action.query.filter_by(request_id=submission.request_id).first()
        if existing_action:
            logging.warning(
                f"[BINGO] DUPLICATE DETECTED: request_id={submission.request_id!r} already processed "
                f"(action_id={existing_action.id}). Skipping."
            )
            return []

    # Check if user is a team member in this event
    # Load Team eagerly via the join to avoid a redundant second query
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
        date=datetime.now(timezone.utc),
        request_id=submission.request_id
    )
    db.session.add(action)
    db.session.commit()
    logging.info(f"[BINGO] Action created: id={action.id}, player={user.runescape_name}, trigger={submission.trigger!r}, team={team.name if team else 'none'}")

    # Write to Firestore (backwards compatibility) — fire-and-forget in background thread
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

    # Check for bingos using batch query (1 query instead of ~40)
    bingo_count = check_bingos_for_completed_tiles(completed_task_tile_indices, team, event)

    # Award bonus points for bingos using atomic SQL UPDATE
    if bingo_count > 0:
        db.session.execute(
            text("UPDATE new_stability.teams SET points = points + :pts, updated_at = NOW() WHERE id = :team_id"),
            {"pts": bingo_count * 15, "team_id": str(team.id)}
        )
        db.session.commit()

    # Refresh team to get accurate points after atomic updates
    db.session.refresh(team)

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
