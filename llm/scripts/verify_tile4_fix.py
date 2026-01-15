#!/usr/bin/env python3
"""
Verify that Tile 4 Task 3 has been properly fixed
"""

from app import app, db
from models.new_events import Tile, Task, Challenge

def main():
    with app.app_context():
        # Find Tile 4
        tile4 = Tile.query.filter_by(index=4, name="Glow-ee Hole").first()

        if not tile4:
            print("ERROR: Tile 4 not found")
            return

        # Get Task 3
        tasks = Task.query.filter_by(tile_id=tile4.id).order_by(Task.name).all()
        task3 = tasks[2]  # Third task

        print(f"Tile 4: {tile4.name}")
        print(f"Task 3: {task3.name}")
        print()

        # Get challenges
        challenges = Challenge.query.filter_by(task_id=task3.id).all()
        parent = [c for c in challenges if c.parent_challenge_id is None][0]

        print(f"Parent Challenge:")
        print(f"  ID: {parent.id}")
        print(f"  Quantity: {parent.quantity}")
        print(f"  Trigger ID: {parent.trigger_id}")
        print()

        # Get children
        children = Challenge.query.filter_by(parent_challenge_id=parent.id).all()
        print(f"Child Challenges ({len(children)} total):")

        all_null = True
        for child in children:
            trigger_name = child.trigger.name if child.trigger else "No trigger"
            qty_status = "NULL ✅" if child.quantity is None else f"{child.quantity} ❌"
            print(f"  - {trigger_name}: quantity={qty_status}")

            if child.quantity is not None:
                all_null = False

        print()
        if all_null:
            print("✅ All child challenges are repeatable (quantity=NULL)")
            print("✅ Duplicates will now count towards the parent's total!")
        else:
            print("❌ Some children still have defined quantities")

if __name__ == "__main__":
    main()
