from datetime import datetime, timezone
from app import db
from event_handlers.event_handler import EventSubmission, NotificationResponse, NotificationAuthor
from models.models import Events
from helper.jsonb import update_jsonb_field
import random

kc_point_dict = {
    "spindel": 1,
    "artio": 1,
    "calvar'ion": 1,
    "venenatis": 1,
    "vet'ion": 1,
    "callisto": 1,
}

item_point_dict = {
    "dragon pickaxe": 20,
    "dragon 2h sword": 20,
    "claws of callisto": 20,
    "fangs of venenatis": 20,
    "skull of vet'ion": 20,
    "treasonous ring": 50,
    "ring of the gods": 50,
    "tyrannical ring": 50,
    "voidwaker hilt": 30,
    "voidwaker blade": 30,
    "voidwaker gem": 30,
    "vet'ion jr.": 100,
    "callisto cub": 100,
    "venenatis spiderling": 100,
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

    if submission.type not in ["KC", "DROP"]:
        return None

    if submission.type == "KC":
        # Check if the trigger is in the kc_point_dict
        if submission.trigger.lower() in kc_point_dict:
            # Use the helper function to modify event.data
            update_jsonb_field(event, "data", lambda data: data.update({submission.rsn: data.get("points", 0) + kc_point_dict[submission.trigger.lower()]}))

            db.session.commit()

            return None # Dont post notification for KC submissions
    elif submission.type == "DROP":
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
                thumbnailImage="https://oldschool.runescape.wiki/images/Wilderness.png?ed6e2",
                author=NotificationAuthor(name=f"{submission.rsn}"),
                description=f"Their current point total is now {new_points} points."
            )]

    return None