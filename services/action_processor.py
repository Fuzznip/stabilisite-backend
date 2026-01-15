from app import db, firestore_db
from models.new_events import (
    Event, Team, TeamMember, Action, Trigger, Challenge, Task, Tile,
    ChallengeStatus, TaskStatus, TileStatus, ChallengeProof
)
from models.models import Users
from services.challenge_evaluator import ChallengeEvaluator
from services.bingo_service import BingoService
from services.notification_builder import NotificationBuilder
from event_handlers.event_handler import NotificationResponse
from sqlalchemy import func
from datetime import datetime, timezone
from typing import Optional, List
import logging

class ActionProcessor:
    """
    Main service for processing player actions and updating event progress.
    """

    @staticmethod
    def process_action(
        player_id: str,
        action_name: str,
        action_type: str = 'DROP',
        source: Optional[str] = None,
        quantity: int = 1,
        date: Optional[datetime] = None
    ) -> dict:
        """
        Process a player action and update all relevant event progress.

        Args:
            player_id: User UUID (from existing Users table)
            action_name: Name of the action/drop/kill
            action_type: Type of action (KC, DROP, QUEST, ACHIEVEMENT, DIARY, SKILL)
            source: Where it came from (boss, location, etc.)
            quantity: How many
            date: When it happened (defaults to now)

        Returns:
            dict with notifications and summary
        """
        if date is None:
            date = datetime.now(timezone.utc)

        # 1. Create Action record
        action = Action(
            player_id=player_id,
            type=action_type,
            name=action_name,
            source=source,
            quantity=quantity,
            date=date
        )
        db.session.add(action)
        db.session.commit()

        logging.info(f"Action created: {action_type} - {action_name} x{quantity} from {source} by user {player_id}")

        # 2. Find all active events
        now = datetime.now(timezone.utc)
        active_events = Event.query.filter(
            Event.start_date <= now,
            Event.end_date >= now
        ).all()

        if not active_events:
            logging.info("No active events found")
            return {"notifications": [], "events_processed": 0}

        all_notifications = []
        events_processed = 0

        # 3. Process action for each active event
        for event in active_events:
            notifications = ActionProcessor._process_action_for_event(
                action=action,
                event=event,
                player_id=player_id
            )
            all_notifications.extend(notifications)
            if notifications:
                events_processed += 1

        return {
            "notifications": [n.to_dict() for n in all_notifications],
            "events_processed": events_processed,
            "action_id": str(action.id)
        }

    @staticmethod
    def _process_action_for_event(
        action: Action,
        event: Event,
        player_id: str
    ) -> List[NotificationResponse]:
        """
        Process an action for a specific event.

        Returns:
            List of notification responses
        """
        # Find player's team in this event
        team = ActionProcessor._find_player_team(player_id, event.id)
        if not team:
            logging.debug(f"User {player_id} not in event {event.id}")
            return []

        logging.info(f"Processing action for team {team.name} in event {event.name}")

        # Match action to triggers
        matched_challenges = ActionProcessor._match_action_to_triggers(
            action=action,
            event_id=event.id
        )

        if not matched_challenges:
            logging.debug(f"No matching triggers found for action {action.name}")
            return []

        # Track all task completions (may be multiple per challenge due to parent completion)
        all_task_completions = []

        # Process each matched challenge
        for challenge in matched_challenges:
            results = ActionProcessor._process_challenge_match(
                challenge=challenge,
                team=team,
                action=action
            )

            # _process_challenge_match now returns a list of results
            for result in results:
                if result and result.get('task_completed'):
                    all_task_completions.append(result)

        # Generate notifications for all task completions
        notifications = []

        # Refresh team to get updated points (from task completions and bingos)
        db.session.refresh(team)

        for completion in all_task_completions:
            tile_id = completion['tile_id']
            medal_level = completion['new_medal_level']
            bingos_awarded = completion.get('bingos_awarded', 0)

            tile = Tile.query.filter_by(id=tile_id).first()
            if not tile:
                continue

            if bingos_awarded > 0:
                # Bingo notification (bingos were already awarded in _check_and_process_task_completion)
                notification = NotificationBuilder.build_bingo_notification(
                    event=event,
                    team=team,
                    bingo_count=bingos_awarded,
                    medal_level=medal_level
                )
                notifications.append(notification)
            else:
                # Task completion notification (no bingo)
                notification = NotificationBuilder.build_task_completion_notification(
                    event=event,
                    team=team,
                    tile=tile,
                    medal_level=medal_level
                )
                notifications.append(notification)

        return notifications

    @staticmethod
    def _find_player_team(player_id: str, event_id: str) -> Optional[Team]:
        """
        Find which team a player is on for a specific event.

        Args:
            player_id: User UUID
            event_id: Event UUID

        Returns:
            Team object or None
        """
        team_member = TeamMember.query.join(Team).filter(
            Team.event_id == event_id,
            TeamMember.user_id == player_id
        ).first()

        if not team_member:
            return None

        return Team.query.filter_by(id=team_member.team_id).first()

    @staticmethod
    def _match_action_to_triggers(action: Action, event_id: str) -> List[Challenge]:
        """
        Find all challenges in the event that match the action's trigger.

        Uses case-insensitive matching and wildcard source matching.

        Args:
            action: The action to match
            event_id: The event ID to search within

        Returns:
            List of matching Challenge objects
        """
        # Normalize action for matching
        action_name_lower = action.name.lower() if action.name else ""
        action_source_lower = action.source.lower() if action.source else ""

        # Get all triggers that match
        # 1. Trigger name matches (case-insensitive)
        # 2. Source matches OR trigger source is empty (wildcard)
        matching_triggers = Trigger.query.filter(
            func.lower(Trigger.name) == action_name_lower
        ).all()

        # Filter by source
        matched_trigger_ids = []
        for trigger in matching_triggers:
            trigger_source_lower = trigger.source.lower() if trigger.source else ""

            # Empty trigger source = wildcard (matches any action source)
            # OR exact match
            if not trigger_source_lower or trigger_source_lower == action_source_lower:
                matched_trigger_ids.append(trigger.id)

        if not matched_trigger_ids:
            return []

        # Find all LEAF challenges (have trigger_id, not parent) in this event that use these triggers
        # Need to join through: Challenge -> Task -> Tile -> Event
        matched_challenges = Challenge.query.join(Task).join(Tile).filter(
            Tile.event_id == event_id,
            Challenge.trigger_id.in_(matched_trigger_ids)
        ).all()

        return matched_challenges

    @staticmethod
    def _should_create_proof(
        challenge: Challenge,
        team: Team,
        challenge_status: ChallengeStatus
    ) -> bool:
        """
        Determine if we should create a proof for this challenge.

        Optimization: Only create proofs for tasks that are:
        1. Not yet completed (avoid redundant proofs for lower difficulty tasks)
        2. Currently being worked on (the "active" task for the tile)

        This prevents creating 3 proofs per action when a tile has bronze/silver/gold tasks
        that all match the same trigger.

        Args:
            challenge: The challenge being processed
            team: The team
            challenge_status: The updated challenge status

        Returns:
            True if proof should be created, False to skip
        """
        if not challenge.task_id:
            # No task associated, always create proof (for parent challenges)
            return True

        # Get the task
        task = Task.query.filter_by(id=challenge.task_id).first()
        if not task:
            return False

        # Check if task is already completed
        task_status = TaskStatus.query.filter_by(
            team_id=team.id,
            task_id=task.id
        ).first()

        if task_status and task_status.completed:
            # Task already completed before this action - skip proof
            return False

        # Check if this action just completed the challenge
        if challenge_status.completed:
            # Challenge just completed - definitely create proof
            return True

        # Challenge not complete yet - check if this is the "active" task for the tile
        # (i.e., the lowest difficulty task that isn't completed yet)
        tile = Tile.query.filter_by(id=task.tile_id).first()
        if not tile:
            return False

        # Get tile status to see current progress level
        tile_status = TileStatus.query.filter_by(
            team_id=team.id,
            tile_id=tile.id
        ).first()

        if not tile_status:
            # No tile status yet - this is the first task, create proof
            return True

        # Get all tasks for this tile ordered by difficulty (we'll assume task order represents difficulty)
        tile_tasks = Task.query.filter_by(tile_id=tile.id).order_by(Task.id).all()

        # Find which task index we're at (based on tasks_completed)
        # tasks_completed: 0=none, 1=bronze, 2=silver, 3=gold
        current_task_index = tile_status.tasks_completed

        if current_task_index >= len(tile_tasks):
            # All tasks completed - shouldn't happen, but skip proof
            return False

        # Get the current active task
        active_task = tile_tasks[current_task_index]

        # Only create proof if this challenge belongs to the active task
        return task.id == active_task.id

    @staticmethod
    def _process_challenge_match(
        challenge: Challenge,
        team: Team,
        action: Action
    ) -> List[dict]:
        """
        Process a matched challenge: update status, check completion, propagate.

        Returns:
            List of task completion results (may be multiple if parent challenges also complete tasks)
        """
        # Update challenge status
        challenge_status = ChallengeEvaluator.update_challenge_status(
            challenge_id=challenge.id,
            team_id=team.id,
            quantity_to_add=action.quantity
        )

        if not challenge_status:
            return []

        # Only create proof if this task is relevant (not already completed)
        should_create_proof = ActionProcessor._should_create_proof(challenge, team, challenge_status)

        if should_create_proof:
            proof = ChallengeProof(
                challenge_status_id=challenge_status.id,
                action_id=action.id
            )
            db.session.add(proof)
            db.session.commit()
        else:
            logging.debug(f"Skipping proof creation for already-completed task (challenge {challenge.id})")

        # Propagate to parent challenges if any
        newly_completed_parents = ChallengeEvaluator.propagate_parent_completion(challenge, team.id)

        # Collect all challenges to check for task completion (leaf + any completed parents)
        challenges_to_check = [challenge]

        # Add any newly completed parents that have task_ids
        for parent_id in newly_completed_parents:
            parent = Challenge.query.filter_by(id=parent_id).first()
            if parent and parent.task_id:
                challenges_to_check.append(parent)

        # Try to complete tasks for all relevant challenges
        results = []
        for chall in challenges_to_check:
            result = ActionProcessor._check_and_process_task_completion(chall, team)
            if result:
                results.append(result)

        # Return ALL successful completions (not just the first)
        return results

    @staticmethod
    def _check_and_process_task_completion(
        challenge: Challenge,
        team: Team
    ) -> Optional[dict]:
        """
        Check if a challenge's task is complete and process it.

        Args:
            challenge: Challenge to check task for
            team: Team

        Returns:
            dict with completion info or None
        """
        if not challenge.task_id:
            return None

        task = Task.query.filter_by(id=challenge.task_id).first()
        if not task:
            return None

        # Validate tile exists BEFORE checking task completion
        tile = Tile.query.filter_by(id=task.tile_id).first()
        if not tile:
            logging.error(f"Tile {task.tile_id} not found for task {task.id}")
            return None

        # Check if task is complete
        task_complete = ChallengeEvaluator.is_task_complete(task.id, team.id)

        if not task_complete:
            return None

        # Check if task was ALREADY complete
        existing_task_status = TaskStatus.query.filter_by(
            team_id=team.id,
            task_id=task.id
        ).first()

        if existing_task_status and existing_task_status.completed:
            # Already complete, don't award points again
            return None

        # Task newly completed! Update status
        if existing_task_status:
            existing_task_status.completed = True
        else:
            task_status = TaskStatus(
                team_id=team.id,
                task_id=task.id,
                completed=True
            )
            db.session.add(task_status)

        db.session.commit()

        # Get event_id for bingo detection (use tile.event_id directly)
        event = Event.query.filter_by(id=tile.event_id).first()
        if not event:
            logging.error(f"Event not found for tile {tile.id}")
            return None

        # Update tile status - but first check current medal level to determine bingo delta
        tile_status = TileStatus.query.filter_by(
            team_id=team.id,
            tile_id=tile.id
        ).first()

        # Determine what the new medal level will be after this task completion
        if not tile_status:
            new_medal_level = 1
        else:
            new_medal_level = min(tile_status.tasks_completed + 1, 3)

        # Count bingos BEFORE updating tile status (for delta calculation)
        bingos_before = BingoService.count_bingos_at_level(event.id, team.id, new_medal_level)

        # Now update the tile status
        if not tile_status:
            tile_status = TileStatus(
                team_id=team.id,
                tile_id=tile.id,
                tasks_completed=1
            )
            db.session.add(tile_status)
        else:
            tile_status.tasks_completed = new_medal_level

        # Award 3 points for task completion using atomic SQL UPDATE
        from sqlalchemy import text
        db.session.execute(
            text("""
                UPDATE new_stability.teams
                SET points = points + 3,
                    updated_at = NOW()
                WHERE id = :team_id
            """),
            {"team_id": str(team.id)}
        )
        db.session.commit()

        # Count bingos AFTER updating tile status
        bingos_after = BingoService.count_bingos_at_level(event.id, team.id, new_medal_level)

        # Calculate and award bingo delta
        new_bingos = bingos_after - bingos_before
        if new_bingos > 0:
            # Award bingo points using atomic SQL UPDATE
            bingo_points = new_bingos * 15
            db.session.execute(
                text("""
                    UPDATE new_stability.teams
                    SET points = points + :bingo_points,
                        updated_at = NOW()
                    WHERE id = :team_id
                """),
                {"bingo_points": bingo_points, "team_id": str(team.id)}
            )
            db.session.commit()
            logging.info(f"Team {team.id} awarded {bingo_points} points for {new_bingos} new bingo(s) at medal level {new_medal_level}")

        logging.info(f"Task {task.id} completed for team {team.id} on tile {tile.id}. Medal level: {new_medal_level}")

        return {
            'task_completed': True,
            'tile_id': tile.id,
            'new_medal_level': new_medal_level,
            'event_id': event.id,
            'bingos_awarded': new_bingos
        }

    @staticmethod
    def write_action_to_firestore(action: Action, event_id: str, team_id: str):
        """
        Write action to Firestore for external tracking.
        TODO: Evaluate if still needed.

        Args:
            action: The action to log
            event_id: The event ID
            team_id: The team ID
        """
        try:
            if firestore_db:
                firestore_db.collection("drops").add({
                    "action_id": str(action.id),
                    "event_id": str(event_id),
                    "team_id": str(team_id),
                    "player_id": str(action.player_id),
                    "name": action.name,
                    "source": action.source,
                    "quantity": action.quantity,
                    "date": action.date.isoformat() if action.date else None,
                    "created_at": action.created_at.isoformat() if action.created_at else None
                })
                logging.info(f"Wrote action {action.id} to Firestore")
        except Exception as e:
            logging.exception(f"Failed to write action {action.id} to Firestore: {e}")
