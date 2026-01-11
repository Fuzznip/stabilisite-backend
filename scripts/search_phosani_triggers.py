"""Search for Phosani-related triggers"""

from app import app, db
from models.new_events import Trigger
from sqlalchemy import func

with app.app_context():
    # Search for triggers containing "inquisitor" or "mace"
    print("=== Searching for 'inquisitor' or 'mace' triggers ===")
    triggers = Trigger.query.filter(
        (func.lower(Trigger.name).like('%inquisitor%')) |
        (func.lower(Trigger.name).like('%mace%'))
    ).all()

    for t in triggers:
        print(f"  - {t.name} (ID: {t.id})")

    # Search for triggers containing "nightmare" or "little"
    print("\n=== Searching for 'nightmare' or 'little' triggers ===")
    triggers = Trigger.query.filter(
        (func.lower(Trigger.name).like('%nightmare%')) |
        (func.lower(Trigger.name).like('%little%'))
    ).all()

    for t in triggers:
        print(f"  - {t.name} (ID: {t.id})")

    # Search for triggers with source containing "phosani" or "nightmare"
    print("\n=== Searching by source: 'phosani' or 'nightmare' ===")
    triggers = Trigger.query.filter(
        (func.lower(Trigger.source).like('%phosani%')) |
        (func.lower(Trigger.source).like('%nightmare%'))
    ).all()

    for t in triggers:
        print(f"  - {t.name} from {t.source} (ID: {t.id})")
