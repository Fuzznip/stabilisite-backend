"""Trigger lookup shared by every v2 event type.

Triggers are global rows keyed by (name, source), so two events that both care
about the same item share one. Only the event-specific Challenge that points at
a trigger is per-event.
"""
from app import db
from models.new_events import Trigger


def get_or_create_trigger(
    name: str,
    source: str | None = None,
    type: str = 'DROP',
    wiki_id: int | None = None,
    img_path: str | None = None,
) -> Trigger:
    """Triggers are global and shared across events, keyed by (name, source).

    `source` defaults to None on purpose. Handlers treat a sourceless trigger as
    matching any submission source, so scoring keys on the item name alone —
    which is what lets a KC submission score without Dink's `source` lining up
    exactly.
    """
    trigger = Trigger.query.filter_by(name=name, source=source).first()
    if trigger:
        # Backfill fields a hand-made trigger may be missing. Only ever fill a
        # null: triggers are shared, so overwriting one event's icon from
        # another event's payload would be wrong.
        if wiki_id is not None and trigger.wiki_id is None:
            trigger.wiki_id = wiki_id
        if img_path is not None and trigger.img_path is None:
            trigger.img_path = img_path
        return trigger

    trigger = Trigger(name=name, source=source, type=type, wiki_id=wiki_id, img_path=img_path)
    db.session.add(trigger)
    db.session.flush()
    return trigger


def triggers_for_events(event_ids: list) -> list[Trigger]:
    """Every trigger any v2 event in `event_ids` scores against.

    One resolver per event type, because each hangs its challenges off a
    different anchor: bingo off a tile's tasks, conquest off a territory (with
    optional OR groups in between), botw off a boss container, clog off a slot.
    """
    if not event_ids:
        return []

    trigger_ids: set = set()
    for resolve in (_bingo_trigger_ids, _conquest_trigger_ids, _botw_trigger_ids, _clog_trigger_ids):
        trigger_ids.update(resolve(event_ids))

    if not trigger_ids:
        return []
    return Trigger.query.filter(Trigger.id.in_(trigger_ids)).all()


def _bingo_trigger_ids(event_ids: list) -> set:
    """Tile → Task → Challenge → Trigger."""
    from models.new_events import Challenge, Task, Tile
    rows = (
        db.session.query(Challenge.trigger_id)
        .join(Task, Task.id == Challenge.task_id)
        .join(Tile, Tile.id == Task.tile_id)
        .filter(Tile.event_id.in_(event_ids), Challenge.trigger_id.isnot(None))
        .all()
    )
    return {r[0] for r in rows}


def _conquest_trigger_ids(event_ids: list) -> set:
    """Territory → root challenge → optional OR group → leaf. Three levels deep."""
    from models.new_events import Challenge, Region, Territory
    root_ids = [
        r[0] for r in db.session.query(Territory.challenge_id)
        .join(Region, Region.id == Territory.region_id)
        .filter(Region.event_id.in_(event_ids), Territory.challenge_id.isnot(None))
        .all()
    ]
    if not root_ids:
        return set()

    mid_ids = [
        r[0] for r in db.session.query(Challenge.id)
        .filter(Challenge.parent_challenge_id.in_(root_ids), Challenge.trigger_id.is_(None))
        .all()
    ]

    rows = (
        db.session.query(Challenge.trigger_id)
        .filter(Challenge.trigger_id.isnot(None))
        .filter(
            Challenge.id.in_(root_ids)
            | Challenge.parent_challenge_id.in_(root_ids)
            | (Challenge.parent_challenge_id.in_(mid_ids) if mid_ids else db.false())
        )
        .all()
    )
    return {r[0] for r in rows}


def _botw_trigger_ids(event_ids: list) -> set:
    """Boss container → KC and drop leaves."""
    from models.new_events import BotwBoss, Challenge
    container_ids = [
        r[0] for r in db.session.query(BotwBoss.challenge_id)
        .filter(BotwBoss.event_id.in_(event_ids), BotwBoss.challenge_id.isnot(None))
        .all()
    ]
    if not container_ids:
        return set()

    rows = (
        db.session.query(Challenge.trigger_id)
        .filter(Challenge.parent_challenge_id.in_(container_ids), Challenge.trigger_id.isnot(None))
        .all()
    )
    return {r[0] for r in rows}


def _clog_trigger_ids(event_ids: list) -> set:
    """Slot → challenge → trigger. Flat: a slot's challenge is its own leaf."""
    from models.new_events import Challenge, ClogSlot
    rows = (
        db.session.query(Challenge.trigger_id)
        .join(ClogSlot, ClogSlot.challenge_id == Challenge.id)
        .filter(ClogSlot.event_id.in_(event_ids), Challenge.trigger_id.isnot(None))
        .all()
    )
    return {r[0] for r in rows}
