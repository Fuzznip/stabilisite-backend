"""Add Ancient hilt to Full Godsword task

The Full Godsword task should have:
- Grandparent (require_all=True, quantity=4)
  - 3 shard children
  - Hilt parent (require_all=False, quantity=1)
    - Armadyl godsword hilt
    - Bandos godsword hilt
    - Saradomin godsword hilt
    - Zamorak godsword hilt
    - Ancient hilt (MISSING - need to add)
"""

from app import app, db
from models.new_events import Task, Challenge, Trigger
from sqlalchemy import func

with app.app_context():
    # Find the Full Godsword task
    task = Task.query.join(Task.tile).filter(
        func.lower(Task.name).like('%full%godsword%')
    ).first()

    if not task:
        print("Full Godsword task not found")
        exit(1)

    print(f"Found task: {task.name} (ID: {task.id})")

    # Get all challenges
    all_challenges = Challenge.query.filter_by(task_id=task.id).all()

    # Find the hilt parent (should have children and no trigger)
    hilt_parent = None
    for c in all_challenges:
        if not c.trigger_id:  # Parent challenge
            # Check if it has hilt children
            children = [ch for ch in all_challenges if ch.parent_challenge_id == c.id]
            if children and any('hilt' in (ch.trigger.name.lower() if ch.trigger_id else '') for ch in children):
                hilt_parent = c
                print(f"Found hilt parent (ID: {hilt_parent.id})")
                break

    if not hilt_parent:
        print("ERROR: Could not find hilt parent challenge")
        exit(1)

    # Find Ancient hilt trigger
    ancient_hilt_trigger = Trigger.query.filter(
        func.lower(Trigger.name) == "ancient hilt"
    ).first()

    if not ancient_hilt_trigger:
        print("ERROR: Ancient hilt trigger not found!")
        exit(1)

    print(f"Found Ancient hilt trigger (ID: {ancient_hilt_trigger.id})")

    # Check if Ancient hilt challenge already exists
    existing = Challenge.query.filter_by(
        task_id=task.id,
        trigger_id=ancient_hilt_trigger.id
    ).first()

    if existing:
        print("Ancient hilt challenge already exists!")
    else:
        # Add Ancient hilt as child of hilt parent
        ancient_hilt_child = Challenge(
            task_id=task.id,
            trigger_id=ancient_hilt_trigger.id,
            parent_challenge_id=hilt_parent.id,
            require_all=False,
            quantity=1,
            value=1
        )
        db.session.add(ancient_hilt_child)
        db.session.commit()
        print(f"✅ Added Ancient hilt child to hilt parent (trigger: {ancient_hilt_trigger.id})")

    # Verify final structure
    print("\n=== Final Hilt Parent Structure ===")
    all_challenges = Challenge.query.filter_by(task_id=task.id).all()

    hilt_children = [c for c in all_challenges if c.parent_challenge_id == hilt_parent.id]
    print(f"Hilt parent has {len(hilt_children)} children:")
    for child in hilt_children:
        if child.trigger_id:
            print(f"  - {child.trigger.name}")
