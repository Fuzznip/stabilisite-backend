"""Boss of the week: building bosses from a supplied drop list, and scoring reads.

A boss is a container Challenge with two kinds of children:

    container (no trigger, value 0)
    ├── KC challenge     — Trigger(type=KC), count_per_action=1
    └── drop challenge×N — Trigger(type=DROP), one per drop you configure

Every challenge is repeatable (quantity=NULL), so it accumulates forever and
never completes: a second Awakener's orb is worth as much as the first.

The drop list is stated outright rather than derived from the collection log.
Nothing here reads CollectionLogItem.
"""
from app import db
from models.models import Users
from models.new_events import BotwBoss, Challenge, ChallengeStatus, Trigger
from sqlalchemy import func, null

# Dink reports a kill count as the player's *total* kills at that boss, so
# progress must advance by one kill per submission rather than by the payload's
# quantity. See stabiliserver's kill_count_handler.
KC_COUNT_PER_ACTION = 1

# A challenge with a NULL quantity accumulates forever and never completes.
REPEATABLE = null()


def get_or_create_trigger(
    name: str,
    source: str | None = None,
    type: str = 'DROP',
    wiki_id: int | None = None,
    img_path: str | None = None,
) -> Trigger:
    """Triggers are global and shared across events, keyed by (name, source).

    `source` defaults to None on purpose. The handler treats a sourceless
    trigger as matching any submission source, so scoring keys on the item name
    alone — which is what lets a KC submission score without Dink's `source`
    lining up exactly.
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


def _add_drop_challenge(
    container_id,
    name: str,
    value: int,
    source: str | None = None,
    img_path: str | None = None,
    wiki_id: int | None = None,
) -> Challenge:
    """Attach one drop challenge to a boss's container. Caller commits."""
    trigger = get_or_create_trigger(
        name, source=source, type='DROP', wiki_id=wiki_id, img_path=img_path,
    )
    challenge = Challenge(
        parent_challenge_id=container_id,
        trigger_id=trigger.id,
        quantity=REPEATABLE,
        value=value,
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge


def create_boss(
    event_id,
    name: str,
    kc_points: int = 1,
    drop_points: int = 1,
    drops: list[dict] | None = None,
    image_url: str | None = None,
    display_order: int | None = None,
) -> BotwBoss:
    """Create a boss and its whole challenge tree from an explicit drop list.

    Each entry in `drops` is `{name, points?, img_path?, source?, wiki_id?}`;
    `points` falls back to `drop_points`. An empty list is legal and yields a
    KC-only boss, which is a real configuration for a kills-only week.
    """
    # REPEATABLE, not None: Challenge.quantity carries a column default of 1, and
    # SQLAlchemy applies that default to an attribute explicitly set to None. Only
    # a SQL NULL literal actually stores NULL, which is what marks a challenge as
    # never-completing.
    container = Challenge(task_id=None, trigger_id=None, quantity=REPEATABLE, value=0)
    db.session.add(container)
    db.session.flush()

    kc_trigger = get_or_create_trigger(name, type='KC')
    db.session.add(Challenge(
        parent_challenge_id=container.id,
        trigger_id=kc_trigger.id,
        quantity=REPEATABLE,
        value=kc_points,
        count_per_action=KC_COUNT_PER_ACTION,
    ))

    for drop in drops or []:
        _add_drop_challenge(
            container.id,
            name=drop['name'],
            value=drop.get('points', drop_points),
            source=drop.get('source'),
            img_path=drop.get('img_path'),
            wiki_id=drop.get('wiki_id'),
        )

    boss = BotwBoss(
        event_id=event_id,
        name=name,
        image_url=image_url,
        display_order=display_order,
        challenge_id=container.id,
    )
    db.session.add(boss)
    db.session.commit()
    return boss


def add_drop(boss: BotwBoss, drop: dict, default_points: int = 1) -> Challenge:
    """Append one drop to an existing boss."""
    challenge = _add_drop_challenge(
        boss.challenge_id,
        name=drop['name'],
        value=drop.get('points', default_points),
        source=drop.get('source'),
        img_path=drop.get('img_path'),
        wiki_id=drop.get('wiki_id'),
    )
    db.session.commit()
    return challenge


def find_boss_drop(challenge_id) -> Challenge | None:
    """A drop challenge, only if it really belongs to a BOTW boss.

    Guards the delete route: without this check any challenge id — a bingo tile's,
    a conquest territory's — would be deletable through it.
    """
    return (
        db.session.query(Challenge)
        .join(BotwBoss, BotwBoss.challenge_id == Challenge.parent_challenge_id)
        .filter(Challenge.id == challenge_id)
        .first()
    )


def boss_challenges(boss: BotwBoss) -> list[tuple[Challenge, Trigger]]:
    """The boss's scoring challenges paired with their triggers, KC first."""
    if not boss.challenge_id:
        return []

    rows = (
        db.session.query(Challenge, Trigger)
        .join(Trigger, Trigger.id == Challenge.trigger_id)
        .filter(Challenge.parent_challenge_id == boss.challenge_id)
        .all()
    )
    return sorted(rows, key=lambda r: (r[1].type != 'KC', r[1].name.lower()))


def serialize_boss(boss: BotwBoss) -> dict:
    data = boss.serialize()
    data['challenges'] = [
        {**challenge.serialize(), 'trigger': trigger.serialize()}
        for challenge, trigger in boss_challenges(boss)
    ]
    return data


def leaderboard(event_id) -> list[dict]:
    """Player standings for an event, broken down per boss.

    Points are computed here rather than stored, so editing a challenge's value
    mid-event corrects every score already earned on it.

    Each boss also carries the player's kill count and their per-drop tallies,
    which is what the website renders as the boss icon plus a trigger icon per
    item. ChallengeStatus.quantity is the number of times the trigger fired, so
    it doubles as the kill count on the KC challenge and the drop count on each
    drop challenge.
    """
    rows = (
        db.session.query(
            ChallengeStatus.player_id,
            Users.runescape_name,
            BotwBoss.id.label('boss_id'),
            BotwBoss.name.label('boss_name'),
            BotwBoss.image_url.label('boss_image_url'),
            BotwBoss.display_order.label('display_order'),
            Trigger.id.label('trigger_id'),
            Trigger.name.label('trigger_name'),
            Trigger.type.label('trigger_type'),
            Trigger.img_path.label('trigger_img_path'),
            ChallengeStatus.quantity.label('quantity'),
            ChallengeStatus.id.label('status_id'),
            Challenge.value.label('value'),
        )
        .join(Challenge, Challenge.id == ChallengeStatus.challenge_id)
        .join(Trigger, Trigger.id == Challenge.trigger_id)
        .join(BotwBoss, BotwBoss.challenge_id == Challenge.parent_challenge_id)
        .join(Users, Users.id == ChallengeStatus.player_id)
        .filter(BotwBoss.event_id == event_id, ChallengeStatus.player_id.isnot(None))
        .all()
    )

    players: dict = {}
    for row in rows:
        player = players.setdefault(str(row.player_id), {
            'player_id': str(row.player_id),
            'rsn': row.runescape_name,
            'points': 0,
            'bosses': [],
        })
        bosses = {b['boss_id']: b for b in player['bosses']}
        boss = bosses.get(str(row.boss_id))
        if boss is None:
            boss = {
                'boss_id': str(row.boss_id),
                'boss_name': row.boss_name,
                'image_url': row.boss_image_url,
                'display_order': row.display_order,
                'points': 0,
                'kills': 0,
                'drops': [],
            }
            player['bosses'].append(boss)

        quantity = int(row.quantity or 0)
        points = quantity * int(row.value or 0)
        player['points'] += points
        boss['points'] += points

        if row.trigger_type == 'KC':
            boss['kills'] += quantity
        elif quantity > 0:
            boss['drops'].append({
                'trigger_id': str(row.trigger_id),
                # The status this drop's proofs hang off. The site reads its
                # screenshots from /v2/statuses/challenges/<id>/proofs.
                'status_id': str(row.status_id),
                'name': row.trigger_name,
                'img_path': row.trigger_img_path,
                'quantity': quantity,
                'points': points,
            })

    standings = sorted(players.values(), key=lambda p: (-p['points'], p['rsn'].lower()))
    for rank, player in enumerate(standings, start=1):
        player['rank'] = rank
        # Bosses in the event's configured order so a player's row lines up with
        # the cards above it; drops by value, then name.
        player['bosses'].sort(
            key=lambda b: (
                b['display_order'] if b['display_order'] is not None else 1 << 31,
                b['boss_name'].lower(),
            )
        )
        for boss in player['bosses']:
            boss.pop('display_order', None)
            boss['drops'].sort(key=lambda d: (-d['points'], d['name'].lower()))
    return standings


def player_points(event_id, player_id) -> int:
    """A single player's total for the event."""
    total = (
        db.session.query(func.sum(ChallengeStatus.quantity * Challenge.value))
        .join(Challenge, Challenge.id == ChallengeStatus.challenge_id)
        .join(BotwBoss, BotwBoss.challenge_id == Challenge.parent_challenge_id)
        .filter(
            BotwBoss.event_id == event_id,
            ChallengeStatus.player_id == player_id,
        )
        .scalar()
    )
    return int(total or 0)
