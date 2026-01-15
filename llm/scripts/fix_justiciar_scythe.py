"""Fix 3x Justiciar or Scythe task structure

Structure:
GRANDPARENT (NULL trigger, require_all=False, quantity=1)
├─ Scythe of vitur (direct child)
└─ PARENT: Justiciar pieces (NULL trigger, require_all=False, quantity=3)
   ├─ Justiciar faceguard (value=1)
   ├─ Justiciar chestguard (value=1)
   └─ Justiciar legguards (value=1)
"""

from app import app, db
from models.new_events import Task, Challenge, Trigger
from sqlalchemy import func

with app.app_context():
    # Find the task
    task = Task.query.join(Task.tile).filter(
        func.lower(Task.name).like('%justiciar%scythe%')
    ).first()

    if not task:
        print("Task not found")
        exit(1)

    print(f"Found task: {task.name} (ID: {task.id})")

    # Delete existing challenges
    existing_challenges = Challenge.query.filter_by(task_id=task.id).all()
    print(f"Deleting {len(existing_challenges)} existing challenges...")
    for c in existing_challenges:
        db.session.delete(c)
    db.session.commit()

    # Create grandparent challenge (NULL trigger, require_all=False, quantity=1)
    grandparent = Challenge(
        task_id=task.id,
        trigger_id=None,
        parent_challenge_id=None,
        require_all=False,
        quantity=1,
        value=1
    )
    db.session.add(grandparent)
    db.session.flush()
    print(f"Created grandparent challenge (ID: {grandparent.id})")

    # Create Child 1: Scythe of vitur (direct child with trigger)
    scythe_trigger = Trigger.query.filter(
        func.lower(Trigger.name) == "scythe of vitur"
    ).first()

    if not scythe_trigger:
        print("ERROR: Scythe of vitur trigger not found!")
    else:
        scythe_child = Challenge(
            task_id=task.id,
            trigger_id=scythe_trigger.id,
            parent_challenge_id=grandparent.id,
            require_all=False,
            quantity=1,
            value=1
        )
        db.session.add(scythe_child)
        print(f"Created Scythe child (trigger: {scythe_trigger.id})")

    db.session.flush()

    # Create Child 2/Parent: Justiciar pieces (NULL trigger, require_all=False, quantity=3)
    parent_justiciar = Challenge(
        task_id=task.id,
        trigger_id=None,
        parent_challenge_id=grandparent.id,
        require_all=False,
        quantity=3,
        value=1
    )
    db.session.add(parent_justiciar)
    db.session.flush()
    print(f"Created Justiciar parent (ID: {parent_justiciar.id})")

    # Create Justiciar piece children (3 armor pieces, each value=1)
    justiciar_pieces = [
        "Justiciar faceguard",
        "Justiciar chestguard",
        "Justiciar legguards"
    ]

    for piece_name in justiciar_pieces:
        # Find trigger
        trigger = Trigger.query.filter(
            func.lower(Trigger.name) == piece_name.lower()
        ).first()

        if not trigger:
            print(f"ERROR: Trigger '{piece_name}' not found!")
            continue

        # Create child challenge
        child = Challenge(
            task_id=task.id,
            trigger_id=trigger.id,
            parent_challenge_id=parent_justiciar.id,
            require_all=False,
            quantity=1,
            value=1
        )
        db.session.add(child)
        print(f"  Created Justiciar piece child: {piece_name} (trigger: {trigger.id})")

    db.session.commit()
    print("\n✅ Successfully updated 3x Justiciar or Scythe task!")

    # Verify structure
    print("\n=== Final Structure ===")
    all_challenges = Challenge.query.filter_by(task_id=task.id).all()

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
