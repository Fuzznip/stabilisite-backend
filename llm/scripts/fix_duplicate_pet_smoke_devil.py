#!/usr/bin/env python3
"""
Fix duplicate Pet smoke devil challenge entries
"""

from app import app, db
from models.new_events import Challenge, Trigger, Tile

def main():
    with app.app_context():
        # Find the slayer unique tile
        tile1 = Tile.query.filter_by(index=1, name="Slayer Unique Tile").first()

        if not tile1:
            print("ERROR: Slayer Unique Tile not found")
            return

        print(f"Found tile: {tile1.name}")

        # Find all challenges for this tile's tasks
        from models.new_events import Task
        tasks = Task.query.filter_by(tile_id=tile1.id).all()

        for task in tasks:
            challenges = Challenge.query.filter_by(task_id=task.id).all()
            parent = [c for c in challenges if c.parent_challenge_id is None]

            if parent:
                parent = parent[0]
                children = Challenge.query.filter_by(parent_challenge_id=parent.id).all()

                # Group children by trigger_id
                trigger_map = {}
                for child in children:
                    if child.trigger_id not in trigger_map:
                        trigger_map[child.trigger_id] = []
                    trigger_map[child.trigger_id].append(child)

                # Find duplicates
                for trigger_id, child_list in trigger_map.items():
                    if len(child_list) > 1:
                        trigger = Trigger.query.get(trigger_id)
                        print(f"\n⚠️ Found {len(child_list)} duplicate entries for trigger: {trigger.name if trigger else trigger_id}")

                        # Keep the first one, delete the rest
                        for idx, child in enumerate(child_list):
                            if idx == 0:
                                print(f"  ✓ Keeping challenge {child.id}")
                            else:
                                print(f"  ✗ Deleting duplicate challenge {child.id}")
                                db.session.delete(child)

        print("\nCommitting changes...")
        db.session.commit()
        print("✅ Duplicate challenges removed!")

if __name__ == "__main__":
    main()
