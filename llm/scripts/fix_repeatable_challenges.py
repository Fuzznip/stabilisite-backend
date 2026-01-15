#!/usr/bin/env python3
"""
Find and fix all repeatable challenges:
- Parent challenges with quantity > 1
- In tasks with require_all=False (OR logic)
- Set child challenge quantities to NULL so duplicates count towards parent
"""

from app import app, db
from models.new_events import Task, Challenge, Tile

def main():
    with app.app_context():
        # Find all OR tasks (require_all=False)
        or_tasks = Task.query.filter_by(require_all=False).all()

        print(f"Found {len(or_tasks)} tasks with OR logic (require_all=False)\n")
        print("="*80)

        tasks_to_fix = []

        for task in or_tasks:
            # Get the tile this task belongs to
            tile = Tile.query.filter_by(id=task.tile_id).first()
            tile_name = tile.name if tile else "Unknown Tile"
            tile_index = tile.index if tile else "?"

            # Get all challenges for this task
            challenges = Challenge.query.filter_by(task_id=task.id).all()

            # Find top-level challenges (no parent)
            top_level = [c for c in challenges if c.parent_challenge_id is None]

            # Look for parent challenges with quantity > 1
            for parent in top_level:
                # Skip if parent has a trigger (not a parent structure)
                if parent.trigger_id:
                    continue

                # Parent has no trigger, check if quantity > 1
                if parent.quantity and parent.quantity > 1:
                    # Get children
                    children = Challenge.query.filter_by(parent_challenge_id=parent.id).all()

                    # Count how many children have non-NULL quantities
                    children_with_qty = [c for c in children if c.quantity is not None]

                    if children_with_qty:
                        # This is a task that needs fixing!
                        tasks_to_fix.append({
                            'task': task,
                            'tile_index': tile_index,
                            'tile_name': tile_name,
                            'parent': parent,
                            'children': children,
                            'children_to_fix': children_with_qty
                        })

                        print(f"Tile {tile_index}: {tile_name}")
                        print(f"  Task: {task.name}")
                        print(f"  Parent Challenge: quantity={parent.quantity}")
                        print(f"  Children: {len(children)} total, {len(children_with_qty)} need fixing")

                        for child in children_with_qty:
                            trigger_name = child.trigger.name if child.trigger else "No trigger"
                            print(f"    - {trigger_name}: qty={child.quantity} (will set to NULL)")

                        print()

        print("="*80)
        print(f"\nSummary: Found {len(tasks_to_fix)} tasks with repeatable parent challenges")

        if not tasks_to_fix:
            print("✅ No challenges need fixing!")
            return

        # Ask for confirmation
        print("\nThis script will set child challenge quantities to NULL for the tasks above.")
        print("This allows duplicate submissions to count towards parent progress.")

        response = input("\nProceed with fixes? (yes/no): ")

        if response.lower() != 'yes':
            print("Aborted.")
            return

        # Apply fixes
        print("\nApplying fixes...")
        total_fixed = 0

        for item in tasks_to_fix:
            task_name = item['task'].name
            tile_info = f"Tile {item['tile_index']}: {item['tile_name']}"

            print(f"\n{tile_info} - {task_name}")

            for child in item['children_to_fix']:
                trigger_name = child.trigger.name if child.trigger else "No trigger"
                print(f"  Setting {trigger_name}: qty {child.quantity} -> NULL")
                child.quantity = None
                total_fixed += 1

        db.session.commit()

        print(f"\n{'='*80}")
        print(f"✅ Fixed {total_fixed} child challenges across {len(tasks_to_fix)} tasks!")
        print(f"{'='*80}")

if __name__ == "__main__":
    main()
