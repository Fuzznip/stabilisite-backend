import logging
import random

from app import db
from event_handlers.event_handler import EventSubmission, NotificationResponse, NotificationAuthor
from models.models import Events
from helper.jsonb import update_jsonb_field

description_phrases = [
    "Guys, I think dink is working.",
    "I think that enemy got the point!",
    "Goodbye, my sweet child.",
    "Plugin check: ✅ Gnome check: ❌",
    "Testing successful. Please consider therapy.",
    "Plugin functioning. Gnome child voted off the island.",
    "Plugin confirmed. Gnome child… not so much.",
    "Gnome child has perished. Plugin operational. Morality… questionable.",
    "RIP Gnome Child. Cause of death: Science.",
    "Excellent, the plugin works. And you've failed the Turing test."
]

def gnome_child_bone_handler(submission: EventSubmission) -> list[NotificationResponse]:
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    event = Events.query.filter(
        Events.type == "DINK_TEST",
        Events.start_time <= now,
        Events.end_time >= now,
    ).first()

    if not event:
        logging.info("[GNOME_CHILD] No active event, skipping")
        return []

    logging.info(f"[GNOME_CHILD] Matched — event={event.name!r} ({event.id})")

    if submission.trigger.lower() == "bones" and submission.source.lower() == "gnome child":
        # Use the helper function to modify event.data
        update_jsonb_field(event, "data", lambda data: data.update({"kills": data.get("kills", 0) + 1}))
        
        db.session.commit()
            
        return [NotificationResponse(
            threadId=event.thread_id,
            title=f"The Child has been Slain.",
            color=0xFF5733,  # Example color in hex format
            thumbnailImage="https://i.imgur.com/3UzSw0Q.png",
            author=NotificationAuthor(name=f"{submission.rsn}"),
            description=random.choice(description_phrases)
        )]
    return []
