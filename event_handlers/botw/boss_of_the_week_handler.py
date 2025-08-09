from datetime import datetime, timezone
from app import db
from event_handlers.event_handler import EventSubmission, NotificationResponse, NotificationAuthor
from models.models import Events
from helper.jsonb import update_jsonb_field
import random

kc_point_dict = {
    "corrupted hunllef": 2,
    "crystalline hunllef": 1,
}

item_point_dict = {
    "crystal weapon seed": 20,
    "crystal armour seed": 25,
    "enhanced crystal weapon seed": 60,
    "youngllef": 80,
}

def botw_handler(submission: EventSubmission) -> list[NotificationResponse]:
    # Grab the most recent 'Boss of the Week' event
    now = datetime.now(timezone.utc)
    event = Events.query.filter(
        Events.start_time <= now, 
        Events.end_time >= now, 
        Events.type == "BOSS_OF_THE_WEEK"
    ).first()

    if event is None:
        return None # Or an empty list

    if submission.type not in ["KC", "LOOT"]:
        return None

    if submission.type == "KC":
        # Check if the trigger is in the kc_point_dict
        if submission.trigger.lower() in kc_point_dict:
            new_points = event.data.get(submission.rsn, 0) + kc_point_dict[submission.trigger.lower()]
            # Use the helper function to modify event.data
            update_jsonb_field(event, "data", lambda data: data.update({submission.rsn: new_points}))

            db.session.commit()

            return None # Dont post notification for KC submissions
    elif submission.type == "LOOT":
        # Check if the item is in the item_point_dict
        if submission.trigger.lower() in item_point_dict and submission.source.lower() in kc_point_dict:
            new_points = event.data.get(submission.rsn, 0) + item_point_dict[submission.trigger.lower()]
            # Use the helper function to modify event.data
            update_jsonb_field(event, "data", lambda data: data.update({submission.rsn: new_points}))

            db.session.commit()

            return [NotificationResponse(
                threadId=event.thread_id,
                title=f"{submission.rsn} has received a {submission.trigger} for {item_point_dict[submission.trigger.lower()]} points!",
                color=0xFF0055,
                thumbnailImage="https://i.imgur.com/55RLPmc.png",
                author=NotificationAuthor(name=f"{submission.rsn}"),
                description=f"Their current point total is now {new_points} points."
            )]

    return None