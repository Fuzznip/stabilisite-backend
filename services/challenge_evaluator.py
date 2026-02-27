from models.new_events import Challenge, ChallengeStatus, Task
from typing import Optional
import logging

class ChallengeEvaluator:
    """
    Evaluates hierarchical challenge completion logic.
    Supports OR/AND logic with nested parent challenges.
    """

    @staticmethod
    def evaluate_challenge(challenge_id: str, team_id: str) -> bool:
        """
        Recursively evaluate if a challenge is complete for a team.

        Args:
            challenge_id: The challenge ID to evaluate
            team_id: The team ID

        Returns:
            True if challenge is complete, False otherwise
        """
        challenge = Challenge.query.filter_by(id=challenge_id).first()
        if not challenge:
            logging.error(f"Challenge {challenge_id} not found")
            return False

        # Check if this is a leaf challenge (has a trigger)
        if challenge.trigger_id:
            return ChallengeEvaluator._evaluate_leaf_challenge(challenge, team_id)

        # Parent challenge (no trigger, has children)
        return ChallengeEvaluator._evaluate_parent_challenge(challenge, team_id)

    @staticmethod
    def _evaluate_leaf_challenge(challenge: Challenge, team_id: str) -> bool:
        """
        Evaluate a leaf challenge (one with a trigger).

        Args:
            challenge: The challenge object
            team_id: The team ID

        Returns:
            True if challenge quantity requirement met, False otherwise
        """
        status = ChallengeStatus.query.filter_by(
            challenge_id=challenge.id,
            team_id=team_id
        ).first()

        if not status:
            return False

        # Check if accumulated quantity meets requirement
        return status.quantity >= challenge.quantity

    @staticmethod
    def _evaluate_parent_challenge(challenge: Challenge, team_id: str) -> bool:
        """
        Evaluate a parent challenge (one with child challenges).

        Parent completion logic:
        - If require_all=False (OR): Parent completes when challenge.quantity children complete
        - If require_all=True (AND): Parent completes when ALL children complete AND meets quantity

        Args:
            challenge: The challenge object
            team_id: The team ID

        Returns:
            True if parent challenge logic satisfied, False otherwise
        """
        # Get all child challenges
        children = Challenge.query.filter_by(parent_challenge_id=challenge.id).all()

        if not children:
            logging.warning(f"Parent challenge {challenge.id} has no children")
            return False

        # Evaluate each child recursively
        child_results = [
            ChallengeEvaluator.evaluate_challenge(child.id, team_id)
            for child in children
        ]

        completed_count = sum(1 for result in child_results if result)

        if challenge.require_all:
            # AND logic: ALL children must complete
            # quantity represents minimum number that must complete (usually same as child count)
            return completed_count >= challenge.quantity and completed_count == len(children)
        else:
            # OR logic: At least challenge.quantity children must complete
            # e.g., "Complete 2 of these 3 challenges"
            return completed_count >= challenge.quantity

    @staticmethod
    def is_task_complete(task_id: str, team_id: str) -> bool:
        """
        Check if a task is complete based on its challenge completion logic.

        Args:
            task_id: The task ID
            team_id: The team ID

        Returns:
            True if task is complete, False otherwise
        """
        task = Task.query.filter_by(id=task_id).first()
        if not task:
            logging.error(f"Task {task_id} not found")
            return False

        # Get all ROOT challenges for this task (parent_challenge_id is null)
        root_challenges = Challenge.query.filter_by(
            task_id=task_id,
            parent_challenge_id=None
        ).all()

        if not root_challenges:
            logging.warning(f"Task {task_id} has no root challenges")
            return False

        # Evaluate each root challenge
        results = [
            ChallengeEvaluator.evaluate_challenge(challenge.id, team_id)
            for challenge in root_challenges
        ]

        if task.require_all:
            # AND logic: ALL root challenges must be complete
            return all(results)
        else:
            # OR logic: ANY root challenge must be complete
            return any(results)

    @staticmethod
    def update_challenge_status(
        challenge_id: str,
        team_id: str,
        quantity_to_add: int
    ) -> Optional[ChallengeStatus]:
        """
        Update or create a challenge status, incrementing quantity.

        Args:
            challenge_id: The challenge ID
            team_id: The team ID
            quantity_to_add: Amount to add to current quantity

        Returns:
            Updated ChallengeStatus or None if error
        """
        from app import db

        challenge = Challenge.query.filter_by(id=challenge_id).first()
        if not challenge:
            logging.error(f"Challenge {challenge_id} not found")
            return None

        # Only leaf challenges (with triggers) can have quantity updated directly
        if not challenge.trigger_id:
            logging.error(f"Cannot update quantity for parent challenge {challenge_id}")
            return None

        # Determine effective quantity to add
        # If count_per_action is set, use that value instead of the action's quantity
        effective_quantity = challenge.count_per_action if challenge.count_per_action is not None else quantity_to_add

        # Get or create status
        status = ChallengeStatus.query.filter_by(
            challenge_id=challenge_id,
            team_id=team_id
        ).first()

        if not status:
            status = ChallengeStatus(
                challenge_id=challenge_id,
                team_id=team_id,
                quantity=effective_quantity,
                completed=False
            )
            db.session.add(status)
            db.session.flush()  # Get the ID without committing
        else:
            # Use atomic SQL UPDATE to prevent race conditions
            # This ensures quantity increment happens at the database level
            from sqlalchemy import text
            db.session.execute(
                text("""
                    UPDATE new_stability.challenge_statuses
                    SET quantity = quantity + :qty,
                        updated_at = NOW()
                    WHERE id = :status_id
                """),
                {"qty": effective_quantity, "status_id": str(status.id)}
            )
            db.session.flush()
            # Refresh to get updated quantity
            db.session.refresh(status)

        # Check if newly completed
        was_completed = status.completed
        status.completed = status.quantity >= challenge.quantity

        db.session.commit()

        # Log if newly completed
        if status.completed and not was_completed:
            logging.info(f"Challenge {challenge_id} completed for team {team_id}")

        return status

    @staticmethod
    def propagate_parent_completion(challenge: Challenge, team_id: str) -> list[str]:
        """
        After a child challenge completes, check and update parent challenge status.
        Returns list of parent challenge IDs that newly completed.

        Args:
            challenge: The child challenge that completed
            team_id: The team ID

        Returns:
            List of parent challenge IDs that newly completed
        """
        from app import db
        from sqlalchemy import text

        newly_completed_parents = []

        # Traverse up the parent chain
        current_challenge = challenge
        while current_challenge.parent_challenge_id:
            parent = Challenge.query.filter_by(id=current_challenge.parent_challenge_id).first()
            if not parent:
                break

            # Get or create parent status
            parent_status = ChallengeStatus.query.filter_by(
                challenge_id=parent.id,
                team_id=team_id
            ).first()

            was_completed = False
            if not parent_status:
                # Create parent status with initial quantity based on child's value
                parent_status = ChallengeStatus(
                    challenge_id=parent.id,
                    team_id=team_id,
                    quantity=current_challenge.value,
                    completed=False
                )
                db.session.add(parent_status)
                db.session.flush()
            else:
                was_completed = parent_status.completed

                # Increment parent quantity by child's value (not just +1)
                db.session.execute(
                    text("""
                        UPDATE new_stability.challenge_statuses
                        SET quantity = quantity + :value,
                            updated_at = NOW()
                        WHERE id = :status_id
                    """),
                    {"value": current_challenge.value, "status_id": str(parent_status.id)}
                )
                db.session.flush()
                # Refresh to get updated quantity
                db.session.refresh(parent_status)

            # Check if parent is now complete
            parent_complete = ChallengeEvaluator.evaluate_challenge(parent.id, team_id)
            parent_status.completed = parent_complete

            # Track newly completed parents
            if parent_complete and not was_completed:
                newly_completed_parents.append(str(parent.id))

            db.session.commit()

            # Only continue propagating up if this parent was newly completed.
            # If the parent didn't complete, its own parent shouldn't be incremented.
            if not parent_complete or was_completed:
                break

            # Move up the chain
            current_challenge = parent

        return newly_completed_parents
