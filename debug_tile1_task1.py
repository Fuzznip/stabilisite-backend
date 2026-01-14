#!/usr/bin/env python3
"""
Debug Tile 1 Task 1 structure
"""

from app import app, db
from models.new_events import Tile, Task, Challenge, ChallengeStatus, TaskStatus, Team

def main():
    with app.app_context():
        # Find Tile 1
        tile1 = Tile.query.filter_by(index=1, name="Slayer Unique Tile").first()
        team = Team.query.filter_by(name="Team Zamorak").first()

        # Get Task 1
        tasks = Task.query.filter_by(tile_id=tile1.id).order_by(Task.name).all()
        task1 = tasks[0]

        print(f"Tile 1: {tile1.name}")
        print(f"Task 1: {task1.name}")
        print(f"  require_all: {task1.require_all}")
        print()

        # Get challenges
        challenges = Challenge.query.filter_by(task_id=task1.id).all()
        top_level = [c for c in challenges if c.parent_challenge_id is None]

        print(f"Top-level challenges: {len(top_level)}")
        for tl in top_level:
            has_trigger = tl.trigger_id is not None
            print(f"  - {'Direct' if has_trigger else 'Parent'} challenge")
            print(f"    Quantity: {tl.quantity}")
            print(f"    Trigger: {tl.trigger.name if has_trigger and tl.trigger else 'None'}")

            if not has_trigger:
                # This is a parent
                children = Challenge.query.filter_by(parent_challenge_id=tl.id).all()
                print(f"    Children: {len(children)}")
                for child in children[:5]:  # Show first 5
                    print(f"      - {child.trigger.name if child.trigger else 'No trigger'}: qty={child.quantity}, value={child.value}")
                if len(children) > 5:
                    print(f"      ... and {len(children) - 5} more")

        print()
        print("=" * 60)
        print("Checking statuses after test...")
        print()

        # Check challenge statuses
        for tl in top_level:
            status = ChallengeStatus.query.filter_by(
                team_id=team.id,
                challenge_id=tl.id
            ).first()

            if status:
                print(f"Top-level challenge status:")
                print(f"  Quantity: {status.quantity}/{tl.quantity}")
                print(f"  Completed: {status.completed}")

        # Check task status
        task_status = TaskStatus.query.filter_by(
            team_id=team.id,
            task_id=task1.id
        ).first()

        if task_status:
            print(f"\nTask status:")
            print(f"  Completed: {task_status.completed}")
        else:
            print(f"\nTask status: Not created yet")

if __name__ == "__main__":
    main()
