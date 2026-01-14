#!/usr/bin/env python3
"""
Fix Parent Challenges - Remove trigger_id from parent challenges

Parent challenges should NOT have a trigger_id. They are containers that track
completion of their children challenges. When a parent has a trigger_id, it
causes the challenge to be matched twice (once as parent, once as child),
leading to incorrect quantity tracking.
"""

from app import app, db
from models.new_events import Challenge

def main():
    with app.app_context():
        # Find all parent challenge IDs
        parent_challenge_ids = db.session.query(Challenge.parent_challenge_id).filter(
            Challenge.parent_challenge_id.isnot(None)
        ).distinct().all()

        parent_ids = [p[0] for p in parent_challenge_ids]
        print(f"Total Parent Challenges: {len(parent_ids)}")

        # Find parents with trigger_id set
        buggy_parents = Challenge.query.filter(
            Challenge.id.in_(parent_ids),
            Challenge.trigger_id.isnot(None)
        ).all()

        print(f"Parents with trigger_id (WILL FIX): {len(buggy_parents)}")

        if not buggy_parents:
            print("✅ No buggy parents found!")
            return

        # Ask for confirmation
        print("\nThis will set trigger_id = NULL for all parent challenges.")
        response = input("Continue? (yes/no): ")

        if response.lower() != 'yes':
            print("Aborted.")
            return

        # Fix each parent
        fixed_count = 0
        for parent in buggy_parents:
            print(f"Fixing Challenge ID: {parent.id} (trigger_id: {parent.trigger_id} → NULL)")
            parent.trigger_id = None
            fixed_count += 1

        # Commit changes
        db.session.commit()

        print(f"\n✅ Fixed {fixed_count} parent challenges!")
        print("Parent challenges no longer have trigger_id set.")

if __name__ == "__main__":
    main()
