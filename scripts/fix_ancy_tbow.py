"""Fix Ancy or Tbow task structure

Structure:
PARENT (NULL trigger, require_all=False, quantity=1)
├─ Twisted bow
├─ Ancestral hat
├─ Ancestral robe top
└─ Ancestral robe bottom
"""

from app import app, db
from models.new_events import Task, Challenge, Trigger
from sqlalchemy import func

with app.app_context():
    # Find the task
    task = Task.query.join(Task.tile).filter(
        func.lower(Task.name).like('%ancy%tbow%')
    ).first()

    if not task:
        print("Task not found")
        exit(1)

    print(f"Found task: {task.name} (ID: {task.id})")

    # Delete all existing challenges
    existing_challenges = Challenge.query.filter_by(task_id=task.id).all()
    print(f"Deleting {len(existing_challenges)} existing challenges...")
    for c in existing_challenges:
        db.session.delete(c)
    db.session.commit()

    # Create parent challenge (NULL trigger, require_all=False, quantity=1)
    parent = Challenge(
        task_id=task.id,
        trigger_id=None,
        parent_challenge_id=None,
        require_all=False,
        quantity=1,
        value=1
    )
    db.session.add(parent)
    db.session.flush()
    print(f"Created parent challenge (ID: {parent.id})")

    # All triggers for this task
    trigger_names = [
        "Twisted bow",
        "Ancestral hat",
        "Ancestral robe top",
        "Ancestral robe bottom"
    ]

    added_count = 0
    for trigger_name in trigger_names:
        # Find trigger
        trigger = Trigger.query.filter(
            func.lower(Trigger.name) == trigger_name.lower()
        ).first()

        if not trigger:
            print(f"ERROR: Trigger '{trigger_name}' not found!")
            continue

        # Create child challenge
        child = Challenge(
            task_id=task.id,
            trigger_id=trigger.id,
            parent_challenge_id=parent.id,
            require_all=False,
            quantity=1,
            value=1
        )
        db.session.add(child)
        added_count += 1
        print(f"  ✓ Added child: {trigger_name} (trigger: {trigger.id})")

    db.session.commit()
    print(f"\n✅ Successfully restructured Ancy or Tbow task with {added_count} children!")

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
