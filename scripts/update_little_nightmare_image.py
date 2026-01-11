"""Update Little nightmare trigger with image URL"""

from app import app, db
from models.new_events import Trigger

with app.app_context():
    # Find the trigger
    trigger = Trigger.query.filter_by(name="Little nightmare").first()

    if not trigger:
        print("ERROR: Little nightmare trigger not found!")
        exit(1)

    print(f"Found trigger: {trigger.name} (ID: {trigger.id})")
    print(f"Current img_path: {trigger.img_path}")

    # Update the image path
    trigger.img_path = "https://oldschool.runescape.wiki/images/Little_nightmare_chathead.png?c7638"
    db.session.commit()

    print(f"✅ Updated img_path to: {trigger.img_path}")
