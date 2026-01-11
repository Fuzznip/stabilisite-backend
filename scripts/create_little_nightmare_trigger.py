"""Create Little nightmare pet trigger"""

from app import app, db
from models.new_events import Trigger

with app.app_context():
    # Check if trigger already exists
    existing = Trigger.query.filter_by(name="Little nightmare").first()

    if existing:
        print(f"Trigger 'Little nightmare' already exists (ID: {existing.id})")
    else:
        # Create the trigger
        trigger = Trigger(
            name="Little nightmare",
            source="Phosani's Nightmare",
            type="DROP"
        )
        db.session.add(trigger)
        db.session.commit()

        print(f"✅ Created trigger 'Little nightmare' (ID: {trigger.id})")
        print(f"   Source: {trigger.source}")
        print(f"   Type: {trigger.type}")
