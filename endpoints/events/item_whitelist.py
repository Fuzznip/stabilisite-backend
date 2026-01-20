from app import app
from helper.helpers import ModelEncoder
from models.models import Events, EventTriggers, EventTriggerMappings
from models.new_events import Event as NewEvent, Trigger as NewTrigger, Challenge, Task, Tile
import json
import logging
from datetime import datetime, timedelta, timezone

@app.route("/events/whitelist", methods=['GET'])
def get_item_whitelist():
    data = {
        "triggers": [],
        "killCountTriggers": [],
        "messageFilters": []
    }

    # Fetch all currently running events and events starting in the next 24 hours
    now = datetime.now(timezone.utc)
    next_24_hours = now + timedelta(hours=24)
    running_events = Events.query.filter(Events.start_time <= next_24_hours).filter(now < Events.end_time).all()
    new_events = NewEvent.query.filter(NewEvent.start_date <= next_24_hours).filter(now < NewEvent.end_date).all()

    if not running_events and not new_events:
        return "No events found", 404

    triggerSet = set()
    messageFilterSet = set()
    killCountTriggerSet = set()

    # Legacy event triggers
    if running_events:
        event_ids = [event.id for event in running_events]
        trigger_mappings = EventTriggerMappings.query.filter(EventTriggerMappings.event_id.in_(event_ids)).all()
        trigger_ids = [mapping.trigger_id for mapping in trigger_mappings]
        triggers = EventTriggers.query.filter(EventTriggers.id.in_(trigger_ids)).all()

        for trigger in triggers:
            if trigger.type == "DROP":
                triggerSet.add(f"{trigger.trigger}:{trigger.source}" if trigger.source else f"{trigger.trigger}")
            elif trigger.type == "KC":
                killCountTriggerSet.add(trigger.trigger)
            else:
                logging.warning(f"Unknown trigger type: {trigger.type}")

    # New event schema triggers
    if new_events:
        new_event_ids = [event.id for event in new_events]
        new_triggers = (
            NewTrigger.query
            .join(Challenge, Challenge.trigger_id == NewTrigger.id)
            .join(Task, Task.id == Challenge.task_id)
            .join(Tile, Tile.id == Task.tile_id)
            .filter(Tile.event_id.in_(new_event_ids))
            .all()
        )

        for trigger in new_triggers:
            if trigger.type == "DROP":
                triggerSet.add(f"{trigger.name}:{trigger.source}" if trigger.source else f"{trigger.name}")
            elif trigger.type == "KC":
                killCountTriggerSet.add(trigger.name)
            else:
                logging.warning(f"Unknown trigger type (new schema): {trigger.type}")

    data["triggers"] = list(triggerSet)
    data["killCountTriggers"] = list(killCountTriggerSet)
    data["messageFilters"] = list(messageFilterSet)
    return json.dumps(data, cls=ModelEncoder)
