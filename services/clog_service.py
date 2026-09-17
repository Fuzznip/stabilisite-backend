"""Collection log race: building an event's slots, and reading its standings.

The collection_log_items catalog is generator input, read once when the event is
created. Slots copy the catalog fields rather than joining, because
scripts/seed_collection_log.py truncates that table on every run.

Triggers are reused across events; challenges never are. A challenge carries the
point value for one event and owns that event's ChallengeStatus rows, so sharing
one between two runs would make a later re-tier rewrite an earlier run's scores
and a later prune cascade away its statuses.
"""
from app import db
from models.models import CollectionLogItem
from models.new_events import Challenge, ChallengeStatus, ClogSlot, Team, Trigger
from services.triggers import get_or_create_trigger

# Only these two tabs are in play. Clues, Minigames and Other are out of scope.
CLOG_CATEGORIES = ('Bosses', 'Raids')

# Boss pages whose drops are worth the raids rate.
HIGH_VALUE_PAGES = ('Nex',)

# The Raids tab is worth the high rate in full; on the Bosses tab only these pages are.
HIGH_VALUE_CATEGORY = 'Raids'

HIGH_VALUE_POINTS = 3
BASE_POINTS = 1


def slot_points(category: str, page: str) -> int:
    if category == HIGH_VALUE_CATEGORY or page in HIGH_VALUE_PAGES:
        return HIGH_VALUE_POINTS
    return BASE_POINTS


def catalog_slots() -> list[dict]:
    """Bosses and Raids catalog rows, one per item_id.

    An item on several boss pages (Dragon pickaxe, Awakener's orb) is one slot.
    The first placement in (page_order, sequence) order becomes its display home.
    """
    rows = (
        CollectionLogItem.query
        .filter(CollectionLogItem.category.in_(CLOG_CATEGORIES))
        .order_by(CollectionLogItem.page_order, CollectionLogItem.sequence)
        .all()
    )

    deduped: dict[int, dict] = {}
    for row in rows:
        if row.item_id in deduped:
            continue
        deduped[row.item_id] = {
            'item_id': row.item_id,
            'name': row.name,
            'category': row.category,
            'page': row.page,
            'page_order': row.page_order,
            'sequence': row.sequence,
            'image_url': row.image_url,
        }
    return list(deduped.values())


def build_slots(event_id) -> list[ClogSlot]:
    """Generate every slot for an event from the catalog. Commits once."""
    slots = []
    for entry in catalog_slots():
        trigger = get_or_create_trigger(
            entry['name'],
            source=None,
            type='DROP',
            wiki_id=entry['item_id'],
            img_path=entry['image_url'],
        )
        challenge = Challenge(
            task_id=None,
            parent_challenge_id=None,
            trigger_id=trigger.id,
            quantity=1,
            value=slot_points(entry['category'], entry['page']),
        )
        db.session.add(challenge)
        db.session.flush()

        slot = ClogSlot(event_id=event_id, challenge_id=challenge.id, **entry)
        db.session.add(slot)
        slots.append(slot)

    db.session.commit()
    return slots


def event_slots(event_id) -> list[tuple[ClogSlot, Challenge]]:
    """Every slot in the event with its challenge, in catalog display order."""
    return (
        db.session.query(ClogSlot, Challenge)
        .join(Challenge, Challenge.id == ClogSlot.challenge_id)
        .filter(ClogSlot.event_id == event_id)
        .order_by(ClogSlot.page_order, ClogSlot.sequence)
        .all()
    )


def serialize_slot(slot: ClogSlot, challenge: Challenge) -> dict:
    data = slot.serialize()
    data['points'] = challenge.value
    return data


def progress(event_id) -> dict:
    """Standings plus a per-team map of completed slots.

    Points are summed here rather than stored, so editing a challenge's value
    mid-event corrects every score already earned on it.
    """
    teams = Team.query.filter_by(event_id=event_id).order_by(Team.name).all()

    rows = (
        db.session.query(ClogSlot.item_id, Challenge.value, ChallengeStatus)
        .join(Challenge, Challenge.id == ClogSlot.challenge_id)
        .join(ChallengeStatus, ChallengeStatus.challenge_id == Challenge.id)
        .filter(ClogSlot.event_id == event_id, ChallengeStatus.completed.is_(True))
        .all()
    )

    completed: dict[str, dict[str, dict]] = {str(t.id): {} for t in teams}
    totals: dict[str, int] = {str(t.id): 0 for t in teams}

    for item_id, value, status in rows:
        team_id = str(status.team_id) if status.team_id else None
        if team_id is None or team_id not in completed:
            continue
        completed[team_id][str(item_id)] = {
            'status_id': str(status.id),
            'points': int(value or 0),
        }
        totals[team_id] += int(value or 0)

    standings = sorted(
        (
            {
                'team_id': str(team.id),
                'name': team.name,
                'color': team.color,
                'image_url': team.image_url,
                'points': totals[str(team.id)],
                'slots_completed': len(completed[str(team.id)]),
            }
            for team in teams
        ),
        key=lambda t: (-t['points'], t['name'].lower()),
    )
    for rank, team in enumerate(standings, start=1):
        team['rank'] = rank

    return {'standings': standings, 'completed': completed}


def delete_slot(slot: ClogSlot) -> None:
    """Remove a slot and its challenge. Statuses cascade with the challenge.

    The FK is ON DELETE SET NULL in the other direction, so deleting the slot row
    alone would orphan the challenge. Delete the challenge explicitly, exactly as
    delete_botw_boss does for its container.
    """
    challenge_id = slot.challenge_id
    db.session.delete(slot)
    db.session.flush()
    if challenge_id:
        Challenge.query.filter_by(id=challenge_id).delete(synchronize_session=False)
    db.session.commit()
