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
from sqlalchemy import text
from models.models import CollectionLogItem
from models.new_events import Challenge, ChallengeStatus, ClogSlot, Team, Trigger
from services.triggers import get_or_create_trigger

# Only these two tabs are in play. Clues, Minigames and Other are out of scope.
CLOG_CATEGORIES = ('Bosses', 'Raids')

# Boss pages whose drops are worth the raids rate.
HIGH_VALUE_PAGES = ('Nex', 'Yama', 'The Nightmare')

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
    The first placement in (page_order, sequence) order becomes its scoring home;
    slot_placements recovers the rest for the board to draw.
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


def _placement(category: str, page: str, page_order, sequence) -> dict:
    return {
        'category': category,
        'page': page,
        'page_order': int(page_order or 0),
        'sequence': int(sequence or 0),
    }


def slot_placements(event_id) -> dict[int, list[dict]]:
    """Every collection log page each of the event's slots appears on.

    A shared drop (Awakener's orb on all four DT2 bosses, Dragon pickaxe on six
    wilderness bosses) is one scored slot, and build_slots keeps only the first
    placement as its home — so the other pages survive nowhere but the catalog.
    Reading them back here rather than storing a copy is what keeps the board
    from drifting out of step with the game's own log.

    seed_collection_log.py truncates and re-inserts that catalog on every run,
    which is why the slots themselves are a frozen snapshot. Only the event's own
    items are looked up, so a re-seed can never add a slot to a running event or
    resurrect a pruned one — the worst it can do is move where an item is drawn,
    which is the point. The slot's stored home is seeded first and never dropped,
    so a re-seed that loses a placement still cannot make an item vanish.

    Returned lists are in display order and always hold at least the home page.
    """
    slots = ClogSlot.query.filter_by(event_id=event_id).all()
    if not slots:
        return {}

    placements = {
        slot.item_id: [
            _placement(slot.category, slot.page, slot.page_order, slot.sequence)
        ]
        for slot in slots
    }

    rows = (
        CollectionLogItem.query
        .filter(CollectionLogItem.category.in_(CLOG_CATEGORIES))
        .all()
    )
    for row in rows:
        entries = placements.get(row.item_id)
        if entries is None:
            continue
        if any(e['category'] == row.category and e['page'] == row.page for e in entries):
            continue
        entries.append(_placement(row.category, row.page, row.page_order, row.sequence))

    for entries in placements.values():
        entries.sort(key=lambda e: (e['page_order'], e['sequence']))
    return placements


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


def serialize_slot(slot: ClogSlot, challenge: Challenge, placements: list[dict] | None = None) -> dict:
    """A slot for the board. `page` stays the scoring home the feed prints;
    `placements` is every page it should be drawn on."""
    data = slot.serialize()
    data['points'] = challenge.value
    data['placements'] = placements or [
        _placement(slot.category, slot.page, slot.page_order, slot.sequence)
    ]
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


def team_players(event_id) -> list[dict]:
    """Every team's roster, each player with the slots they personally claimed.

    Starts from team_members and LEFT JOINs the drops, so a player who has
    claimed nothing still appears with an empty list — a roster that silently
    omitted its quiet half would be worse than useless during a race.

    Attribution comes from the proof: a completed slot has exactly one
    ChallengeProof (duplicates are ignored on the way in), and that proof points
    at the Action carrying the player who got it.
    """
    rows = db.session.execute(text("""
        WITH drops AS (
            SELECT
                cs.team_id,
                a.player_id,
                s.name        AS item_name,
                s.item_id,
                s.page,
                ch.value      AS points,
                cp.img_path,
                cp.created_at
            FROM new_stability.challenge_statuses cs
            JOIN new_stability.challenge_proofs cp ON cp.challenge_status_id = cs.id
            JOIN new_stability.actions          a  ON a.id = cp.action_id
            JOIN new_stability.challenges       ch ON ch.id = cs.challenge_id
            JOIN new_stability.clog_slots       s  ON s.challenge_id = ch.id
            WHERE s.event_id = :event_id
              AND cs.completed IS TRUE
              AND cs.team_id IS NOT NULL
        )
        SELECT
            t.id            AS team_id,
            t.name          AS team_name,
            t.color         AS team_color,
            t.image_url     AS team_image_url,
            u.id            AS player_id,
            u.runescape_name AS player_name,
            d.item_name, d.item_id, d.page, d.points, d.img_path, d.created_at
        FROM new_stability.team_members tm
        JOIN new_stability.teams t ON t.id = tm.team_id
        JOIN users              u ON u.id = tm.user_id
        LEFT JOIN drops        d ON d.team_id = tm.team_id AND d.player_id = u.id
        WHERE t.event_id = :event_id
        ORDER BY t.name, u.runescape_name
    """), {"event_id": str(event_id)}).mappings().all()

    teams: dict = {}
    for row in rows:
        team = teams.setdefault(str(row['team_id']), {
            'team_id': str(row['team_id']),
            'team_name': row['team_name'],
            'team_color': row['team_color'],
            'team_image_url': row['team_image_url'],
            'players': {},
        })
        player = team['players'].setdefault(str(row['player_id']), {
            'player_id': str(row['player_id']),
            'player_name': row['player_name'],
            'points': 0,
            'drops': [],
        })
        if row['item_name'] is None:
            continue
        player['points'] += int(row['points'] or 0)
        player['drops'].append({
            'item_name': row['item_name'],
            'item_id': row['item_id'],
            'page': row['page'],
            'points': int(row['points'] or 0),
            'img_path': row['img_path'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
        })

    result = []
    for team in teams.values():
        players = sorted(
            team['players'].values(),
            key=lambda p: (-p['points'], p['player_name'].lower()),
        )
        for p in players:
            p['drops'].sort(key=lambda d: (-d['points'], d['item_name'].lower()))
        result.append({**team, 'players': players})

    result.sort(key=lambda t: t['team_name'].lower())
    return result


def recent_completions(event_id, page: int = 1, per_page: int = 20, team_id=None) -> dict:
    """Newest-first feed of slots claimed in this event, optionally one team's.

    One row per completion rather than per submission: duplicates never create a
    proof, so every row here is a slot a team took for the first time.

    Paginated because a five-day race across sixty players runs to hundreds of
    entries, and the interesting ones are not always the newest.
    """
    where = "WHERE s.event_id = :event_id AND cs.completed IS TRUE AND cs.team_id IS NOT NULL"
    params = {"event_id": str(event_id)}
    if team_id:
        where += " AND cs.team_id = :team_id"
        params["team_id"] = str(team_id)

    total = db.session.execute(text(f"""
        SELECT COUNT(*)
        FROM new_stability.challenge_statuses cs
        JOIN new_stability.challenge_proofs cp ON cp.challenge_status_id = cs.id
        JOIN new_stability.challenges       ch ON ch.id = cs.challenge_id
        JOIN new_stability.clog_slots       s  ON s.challenge_id = ch.id
        {where}
    """), params).scalar() or 0

    rows = db.session.execute(text(f"""
        SELECT
            cp.id            AS proof_id,
            cs.id            AS status_id,
            s.item_id, s.name AS item_name, s.page,
            ch.value         AS points,
            u.runescape_name AS player_name,
            t.id             AS team_id,
            t.name           AS team_name,
            t.color          AS team_color,
            cp.img_path,
            cp.created_at
        FROM new_stability.challenge_statuses cs
        JOIN new_stability.challenge_proofs cp ON cp.challenge_status_id = cs.id
        JOIN new_stability.actions          a  ON a.id = cp.action_id
        JOIN users                          u  ON u.id = a.player_id
        JOIN new_stability.teams            t  ON t.id = cs.team_id
        JOIN new_stability.challenges       ch ON ch.id = cs.challenge_id
        JOIN new_stability.clog_slots       s  ON s.challenge_id = ch.id
        {where}
        ORDER BY cp.created_at DESC, s.name
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": per_page, "offset": (page - 1) * per_page}).mappings().all()

    pages = (total + per_page - 1) // per_page if per_page else 0
    return {
        "items": [{
            "id": str(r["proof_id"]),
            "status_id": str(r["status_id"]),
            "item_id": r["item_id"],
            "item_name": r["item_name"],
            "page": r["page"],
            "points": int(r["points"] or 0),
            "player_name": r["player_name"],
            "team_id": str(r["team_id"]),
            "team_name": r["team_name"],
            "team_color": r["team_color"],
            "img_path": r["img_path"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        } for r in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }
