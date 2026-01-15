#!/usr/bin/env python3
"""
Fix Tile 4 Task 3 - parent requires 5 but only has 4 children
"""

from app import app, db
from models.new_events import Tile, Task, Challenge

def main():
    with app.app_context():
        tile4 = Tile.query.filter_by(index=4, name="Glow-ee Hole").first()
        
        if not tile4:
            print("ERROR: Tile 4 not found")
            return
        
        tasks = Task.query.filter_by(tile_id=tile4.id).all()
        task3 = tasks[2]
        
        print(f"Fixing Tile 4 Task 3: {task3.id}")
        
        challenges = Challenge.query.filter_by(task_id=task3.id).all()
        parent = [c for c in challenges if c.parent_challenge_id is None][0]
        children = Challenge.query.filter_by(parent_challenge_id=parent.id).all()
        
        print(f"Parent: {parent.id}")
        print(f"  Current quantity: {parent.quantity}")
        print(f"  Number of children: {len(children)}")
        print(f"  Total value: {sum(c.value or 1 for c in children)}")
        
        # Fix: Change parent quantity from 5 to 4
        if parent.quantity == 5 and len(children) == 4:
            print(f"\n  Fixing: Changing parent quantity from 5 to 4")
            parent.quantity = 4
            db.session.commit()
            print("✅ Fixed!")
        else:
            print("\n  Already correct or unexpected state")

if __name__ == "__main__":
    main()
