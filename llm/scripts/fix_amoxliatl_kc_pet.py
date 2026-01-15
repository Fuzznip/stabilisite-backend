"""Fix 600 Amoxliatl KC or Pet task - add parent grouping

Structure:
PARENT (NULL trigger, require_all=False, quantity=1)
├─ Amoxliatl (KC trigger, quantity=600)
└─ Moxi (pet trigger, quantity=1)
"""

from app import app, db
from models.new_events import Task, Challenge, Trigger
from sqlalchemy import func

with app.app_context():
    # Find the task
    task = Task.query.join(Task.tile).filter(
        func.lower(Task.name).like('%amoxliatl%kc%pet%')
    ).first()

    if not task:
        # Try alternative search
        task = Task.query.join(Task.tile).filter(
            func.lower(Task.name).like('%600%amox%')
        ).first()

    if not task:
        print("Task not found")
        exit(1)

    print(f"Found task: {task.name} (ID: {task.id})")
    print(f"Task require_all: {task.require_all}")

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

    # Find triggers
    amoxliatl_trigger = Trigger.query.filter(
        func.lower(Trigger.name) == "amoxliatl"
    ).first()

    pet_trigger = Trigger.query.filter(
        func.lower(Trigger.name) == "moxi"
    ).first()

    if not amoxliatl_trigger:
        print("ERROR: Amoxliatl trigger not found!")
    else:
        # Create KC challenge (600 kills)
        kc_challenge = Challenge(
            task_id=task.id,
            trigger_id=amoxliatl_trigger.id,
            parent_challenge_id=parent.id,
            require_all=False,
            quantity=600,
            value=1
        )
        db.session.add(kc_challenge)
        print(f"  ✓ Added KC child: Amoxliatl (qty=600, trigger: {amoxliatl_trigger.id})")

    if not pet_trigger:
        print("ERROR: Moxi pet trigger not found!")
    else:
        # Create pet challenge
        pet_challenge = Challenge(
            task_id=task.id,
            trigger_id=pet_trigger.id,
            parent_challenge_id=parent.id,
            require_all=False,
            quantity=1,
            value=1
        )
        db.session.add(pet_challenge)
        print(f"  ✓ Added pet child: Moxi (qty=1, trigger: {pet_trigger.id})")

    db.session.commit()
    print("\n✅ Successfully restructured task with parent/child structure!")

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
