#!/usr/bin/env python3
"""
Fix Tile 4 Task 3: Set child challenge quantities to NULL so duplicates count
Parent requires 5 total items, but only has 4 unique children.
Making children repeatable allows duplicates to increment the parent.
"""

from app import app, db
from models.new_events import Tile, Task, Challenge

def main():
    with app.app_context():
        # Find Tile 4 (Glow-ee Hole)
        tile4 = Tile.query.filter_by(index=4, name="Glow-ee Hole").first()

        if not tile4:
            print("ERROR: Tile 4 not found")
            return

        # Get all tasks for this tile
        tasks = Task.query.filter_by(tile_id=tile4.id).order_by(Task.name).all()

        if len(tasks) < 3:
            print(f"ERROR: Expected 3 tasks, found {len(tasks)}")
            return

        # Task 3 is the third task
        task3 = tasks[2]
        print(f"Found Task 3: {task3.name}")
        print(f"  Task ID: {task3.id}")

        # Get all challenges for this task
        challenges = Challenge.query.filter_by(task_id=task3.id).all()

        # Find the parent challenge (no parent_challenge_id)
        parent = [c for c in challenges if c.parent_challenge_id is None][0]
        print(f"\nParent Challenge ID: {parent.id}")
        print(f"  Current quantity: {parent.quantity}")

        # Find all child challenges
        children = Challenge.query.filter_by(parent_challenge_id=parent.id).all()
        print(f"\nFound {len(children)} child challenges:")

        fixed_count = 0
        for child in children:
            trigger_name = child.trigger.name if child.trigger else "No trigger"
            current_qty = child.quantity

            if child.quantity is not None:
                print(f"  ✏️  {trigger_name}: quantity {current_qty} -> NULL (repeatable)")
                child.quantity = None
                fixed_count += 1
            else:
                print(f"  ✅ {trigger_name}: already NULL (repeatable)")

        if fixed_count > 0:
            print(f"\n{'='*60}")
            print(f"Setting {fixed_count} child challenges to repeatable (quantity=NULL)")
            print(f"{'='*60}")

            db.session.commit()
            print("✅ Changes committed!")
            print("\nNow duplicates will count towards the parent's quantity of 5!")
        else:
            print("\n✅ All child challenges already repeatable!")

if __name__ == "__main__":
    main()
