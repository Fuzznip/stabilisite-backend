from datetime import datetime, timezone
from app import db
from event_handlers.event_handler import EventSubmission, NotificationResponse, NotificationAuthor
from models.models import Events
from helper.jsonb import update_jsonb_field
import random

whitelist = [
    "twisted bow",
    "scythe of vitur (uncharged)",
    "sanguinesti staff (uncharged)",
    "averneic defender hilt",
    "justiciar legguards",
    "ghrazi rapier",
    "justiciar chestguard",
    "justiciar faceguard",
    "dexterous prayer scroll",
    "arcane prayer scroll",
    "twisted buckler",
    "dragon hunter crossbow",
    "dinh's bulwark",
    "ancestral hat",
    "ancestral robe top",
    "ancestral robe bottom",
    "dragon claws",
    "elder maul",
    "kodai insignia",
    "twisted bow",
    "osmumten's fang",
    "lightbearer",
    "elidinis' ward",
    "masori mask",
    "masori body",
    "masori chaps",
    "tumeken's shadow (uncharged)"
]

def raid_weekend_event_handler(submission: EventSubmission) -> list[NotificationResponse]:
    # Grab the most recent 'Raid Weekend' event
    now = datetime.now(timezone.utc)
    event = Events.query.filter(
        Events.start_time <= now, 
        Events.end_time >= now, 
        Events.type == "RAID_WEEKEND"
    ).first()

    if event is None:
        return None

    if submission.type not in ["LOOT"]:
        return None

    if submission.type == "LOOT":
        if submission.trigger.lower() in whitelist:
            return [NotificationResponse(
                threadId=event.thread_id,
                title=f"{submission.rsn} has received a {submission.trigger}!",
                color=0xFF0055,
                thumbnailImage="https://media.discordapp.net/attachments/1393688970298265661/1393688970457780295/image.png?ex=687b55c0&is=687a0440&hm=128c7766e8f3df069364b383c829f6f99143e5f25bd43162607a0d456beb75b8&=&format=webp&quality=lossless",
                author=NotificationAuthor(name=f"{submission.rsn}"),
                description=f"Money"
            )]

    return None