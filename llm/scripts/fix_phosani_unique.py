"""Add missing triggers to Phosani unique tile

Missing triggers:
- Inquisitor mace
- Eldritch orb
- Harmonised orb
- Volatile orb
- Jar of dreams
- Little nightmare (pet)
"""

from app import app, db
from models.new_events import Task, Challenge, Trigger
from sqlalchemy import func

with app.app_context():
    # Find the task
    task = Task.query.join(Task.tile).filter(
        func.lower(Task.name).like('%phosani%unique%')
    ).first()

    if not task:
        print("Task not found")
        exit(1)

    print(f"Found task: {task.name} (ID: {task.id})")

    # Get existing challenges
    existing_challenges = Challenge.query.filter_by(task_id=task.id).all()
    print(f"Existing challenges: {len(existing_challenges)}")
    for c in existing_challenges:
        trigger_name = c.trigger.name if c.trigger_id else "NULL"
        print(f"  - {trigger_name}")

    # Missing triggers to add
    missing_triggers = [
        "Inquisitor's mace",
        "Eldritch orb",
        "Harmonised orb",
        "Volatile orb",
        "Jar of dreams",
        "Little nightmare"
    ]

    # Check if this is a parent/child structure
    parent_challenge = None
    for c in existing_challenges:
        if not c.trigger_id:  # Found a parent
            parent_challenge = c
            print(f"\nFound parent challenge (ID: {parent_challenge.id})")
            break

    added_count = 0
    for trigger_name in missing_triggers:
        # Find trigger
        trigger = Trigger.query.filter(
            func.lower(Trigger.name) == trigger_name.lower()
        ).first()

        if not trigger:
            print(f"ERROR: Trigger '{trigger_name}' not found!")
            continue

        # Check if challenge already exists
        existing = Challenge.query.filter_by(
            task_id=task.id,
            trigger_id=trigger.id
        ).first()

        if existing:
            print(f"  Challenge for '{trigger_name}' already exists, skipping")
            continue

        # Create child challenge
        if parent_challenge:
            # Add as child of parent
            child = Challenge(
                task_id=task.id,
                trigger_id=trigger.id,
                parent_challenge_id=parent_challenge.id,
                require_all=False,
                quantity=1,
                value=1
            )
        else:
            # Add as top-level challenge (if no parent exists)
            child = Challenge(
                task_id=task.id,
                trigger_id=trigger.id,
                parent_challenge_id=None,
                require_all=False,
                quantity=1,
                value=1
            )

        db.session.add(child)
        added_count += 1
        print(f"  ✓ Added challenge: {trigger_name} (trigger: {trigger.id})")

    db.session.commit()
    print(f"\n✅ Successfully added {added_count} missing challenges to Phosani unique task!")

    # Verify final structure
    print("\n=== Final Structure ===")
    all_challenges = Challenge.query.filter_by(task_id=task.id).all()
    print(f"Total challenges: {len(all_challenges)}")

    def print_challenge(c, indent=0):
        prefix = "  " * indent
        trigger_name = c.trigger.name if c.trigger_id else "NULL"
        print(f"{prefix}- {trigger_name} (require_all={c.require_all}, qty={c.quantity}, value={c.value})")
        children = [ch for ch in all_challenges if ch.parent_challenge_id == c.id]
        for child in children:
            print_challenge(child, indent + 1)

    roots = [c for c in all_challenges if c.parent_challenge_id is None]
    for root in roots:
        print_challenge(root)
