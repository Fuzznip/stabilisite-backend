"""Fix 3 SR Axe Pieces OR Full Virtus task structure

Structure:
GRANDPARENT (NULL trigger, require_all=False, quantity=1)
├─ PARENT 1: SR Axe Pieces (NULL trigger, require_all=False, quantity=3)
│  ├─ Soulreaper axe piece 1 (value=1)
│  ├─ Soulreaper axe piece 2 (value=1)
│  ├─ Soulreaper axe piece 3 (value=1)
│  └─ Soulreaper axe piece 4 (value=1)
│
└─ PARENT 2: Full Virtus (NULL trigger, require_all=True, quantity=3)
   ├─ Virtus mask (quantity=1)
   ├─ Virtus robe top (quantity=1)
   └─ Virtus robe bottom (quantity=1)
"""

from app import app, db
from models.new_events import Task, Challenge, Trigger
from sqlalchemy import func

with app.app_context():
    # Find the task
    task = Task.query.join(Task.tile).filter(
        func.lower(Task.name).like('%sr axe%virtus%')
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

    # Create Parent 1: SR Axe Pieces (NULL trigger, require_all=False, quantity=3)
    parent_sr_axe = Challenge(
        task_id=task.id,
        trigger_id=None,
        parent_challenge_id=grandparent.id,
        require_all=False,
        quantity=3,
        value=1
    )
    db.session.add(parent_sr_axe)
    db.session.flush()
    print(f"Created SR Axe parent (ID: {parent_sr_axe.id})")

    # Create SR Axe piece children (4 pieces, each value=1)
    sr_axe_pieces = [
        "Executioner's axe head",
        "Siren's staff",
        "Leviathan's lure",
        "Eye of the duke"
    ]

    for piece_name in sr_axe_pieces:
        # Find or create trigger
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
            parent_challenge_id=parent_sr_axe.id,
            require_all=False,
            quantity=1,
            value=1
        )
        db.session.add(child)
        print(f"  Created SR Axe piece child: {piece_name} (trigger: {trigger.id})")

    db.session.flush()

    # Create Parent 2: Full Virtus (NULL trigger, require_all=True, quantity=3)
    parent_virtus = Challenge(
        task_id=task.id,
        trigger_id=None,
        parent_challenge_id=grandparent.id,
        require_all=True,
        quantity=3,
        value=1
    )
    db.session.add(parent_virtus)
    db.session.flush()
    print(f"Created Virtus parent (ID: {parent_virtus.id})")

    # Create Virtus piece children (3 armor pieces, each quantity=1)
    virtus_pieces = [
        "Virtus mask",
        "Virtus robe top",
        "Virtus robe bottom"
    ]

    for piece_name in virtus_pieces:
        # Find or create trigger
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
            parent_challenge_id=parent_virtus.id,
            require_all=False,
            quantity=1,
            value=1
        )
        db.session.add(child)
        print(f"  Created Virtus piece child: {piece_name} (trigger: {trigger.id})")

    db.session.commit()
    print("\n✅ Successfully updated 3 SR Axe Pieces OR Full Virtus task!")

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
