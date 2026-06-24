import json
import queue
import uuid
import logging
from sqlalchemy import text

CONQUEST_SCORING = {
    "TERRITORY_OWNED": 3,
    "REGION_OWNED": 20,
}

# event_id (str) -> set of SimpleQueue instances, one per connected SSE client
sse_clients: dict[str, set[queue.SimpleQueue]] = {}


def broadcast_delta(event_id, log_entries: list[dict]) -> None:
    """Push serialized log entries to all SSE clients watching this event. Called after commit."""
    clients = sse_clients.get(str(event_id), set())
    if not clients:
        return
    payload = json.dumps(log_entries)
    for q in list(clients):
        q.put(payload)


def update_territory_control(territory_id, session) -> dict:
    """
    Recalculate which team controls a territory based on completion counts.
    Tie-break: challenger must strictly exceed the current holder.
    Updates territories.controlling_team_id in place.
    Returns {changed, previous_team_id, new_team_id}.
    """
    root = session.execute(text("""
        SELECT c.quantity, c.trigger_id
        FROM new_stability.territories t
        JOIN new_stability.challenges c ON c.id = t.challenge_id
        WHERE t.id = :territory_id
    """), {"territory_id": str(territory_id)}).fetchone()

    # SINGLE type (root has trigger_id): leaf.quantity already gates via FLOOR, threshold = 1.
    # OR_FLAT/GROUPED (root has no trigger, qty > 1): require score >= root.quantity before capture.
    min_completions = root.quantity if (root and not root.trigger_id and root.quantity > 1) else 1

    rows = session.execute(text("""
        SELECT
            t.id                                                               AS team_id,
            terr.controlling_team_id,
            COALESCE(SUM(COALESCE(leaf.value, 1) * FLOOR(COALESCE(cs.quantity, 0)::numeric / leaf.quantity)), 0) AS completions
        FROM new_stability.territories terr
        JOIN new_stability.regions r ON r.id = terr.region_id
        JOIN new_stability.teams t ON t.event_id = r.event_id
        JOIN new_stability.challenges leaf
            ON leaf.trigger_id IS NOT NULL AND (
                leaf.id = terr.challenge_id
                OR leaf.parent_challenge_id = terr.challenge_id
                OR leaf.parent_challenge_id IN (
                    SELECT id FROM new_stability.challenges
                    WHERE parent_challenge_id = terr.challenge_id
                )
            )
        LEFT JOIN new_stability.challenge_statuses cs
            ON cs.challenge_id = leaf.id AND cs.team_id = t.id
        WHERE terr.id = :territory_id
        GROUP BY t.id, terr.controlling_team_id
        ORDER BY completions DESC
    """), {"territory_id": str(territory_id)}).fetchall()

    if not rows:
        return {"changed": False, "previous_team_id": None, "new_team_id": None}

    current_controller_id = rows[0].controlling_team_id
    leader = rows[0]

    if not leader.completions or int(leader.completions) < min_completions:
        return {"changed": False, "previous_team_id": current_controller_id, "new_team_id": current_controller_id}

    if not current_controller_id:
        new_controller_id = leader.team_id
    else:
        current_count = next(
            (int(r.completions) for r in rows if r.team_id == current_controller_id), 0
        )
        challenger = next(
            (r for r in rows if r.team_id != current_controller_id and int(r.completions) > current_count),
            None
        )
        new_controller_id = challenger.team_id if challenger else current_controller_id

    if new_controller_id == current_controller_id:
        return {"changed": False, "previous_team_id": current_controller_id, "new_team_id": current_controller_id}

    session.execute(text("""
        UPDATE new_stability.territories
        SET controlling_team_id = :controller_id
        WHERE id = :territory_id
    """), {"controller_id": str(new_controller_id), "territory_id": str(territory_id)})

    return {"changed": True, "previous_team_id": current_controller_id, "new_team_id": new_controller_id}


def update_region_control(region_id, session) -> dict:
    """
    Recalculate which team controls a region based on territory counts.
    Tie-break: challenger must strictly exceed the current holder.
    Updates regions.controlling_team_id in place.
    Returns {changed, previous_team_id, new_team_id}.
    """
    rows = session.execute(text("""
        SELECT
            controlling_team_id AS team_id,
            COUNT(*)            AS count
        FROM new_stability.territories
        WHERE region_id = :region_id AND controlling_team_id IS NOT NULL
        GROUP BY controlling_team_id
        ORDER BY count DESC
    """), {"region_id": str(region_id)}).fetchall()

    region = session.execute(text("""
        SELECT controlling_team_id FROM new_stability.regions WHERE id = :region_id
    """), {"region_id": str(region_id)}).fetchone()

    current_controller_id = region.controlling_team_id if region else None

    if not rows:
        return {"changed": False, "previous_team_id": current_controller_id, "new_team_id": None}

    leader = rows[0]

    if not current_controller_id:
        new_controller_id = leader.team_id
    else:
        current_count = next(
            (int(r.count) for r in rows if r.team_id == current_controller_id), 0
        )
        challenger = next(
            (r for r in rows if r.team_id != current_controller_id and int(r.count) > current_count),
            None
        )
        new_controller_id = challenger.team_id if challenger else current_controller_id

    if new_controller_id == current_controller_id:
        return {"changed": False, "previous_team_id": current_controller_id, "new_team_id": current_controller_id}

    session.execute(text("""
        UPDATE new_stability.regions
        SET controlling_team_id = :controller_id
        WHERE id = :region_id
    """), {"controller_id": str(new_controller_id), "region_id": str(region_id)})

    return {"changed": True, "previous_team_id": current_controller_id, "new_team_id": new_controller_id}


def check_green_log(team_id, region_id, session) -> bool:
    """
    Award a green log if this team has >= 1 completion on every territory challenge in the region.
    Append-only: once awarded, never removed.
    Returns True only on the first award.
    """
    region = session.execute(text("""
        SELECT green_logged_teams FROM new_stability.regions WHERE id = :region_id
    """), {"region_id": str(region_id)}).fetchone()

    if not region:
        return False

    team_uuid = uuid.UUID(str(team_id))
    existing = [uuid.UUID(str(t)) for t in (region.green_logged_teams or [])]
    if team_uuid in existing:
        return False

    result = session.execute(text("""
        SELECT
            COUNT(DISTINCT terr.id)                                                          AS total,
            COUNT(DISTINCT terr.id) FILTER (
                WHERE COALESCE(per_terr.leaf_completions, 0) >= CASE
                    WHEN root_c.trigger_id IS NULL AND root_c.quantity > 1 THEN root_c.quantity
                    ELSE 1
                END
            ) AS completed
        FROM new_stability.territories terr
        LEFT JOIN new_stability.challenges root_c ON root_c.id = terr.challenge_id
        LEFT JOIN (
            SELECT
                terr2.id AS territory_id,
                SUM(COALESCE(leaf.value, 1) * FLOOR(COALESCE(cs.quantity, 0)::numeric / leaf.quantity)) AS leaf_completions
            FROM new_stability.territories terr2
            JOIN new_stability.challenges leaf
                ON leaf.trigger_id IS NOT NULL AND (
                    leaf.id = terr2.challenge_id
                    OR leaf.parent_challenge_id = terr2.challenge_id
                    OR leaf.parent_challenge_id IN (
                        SELECT id FROM new_stability.challenges
                        WHERE parent_challenge_id = terr2.challenge_id
                    )
                )
            LEFT JOIN new_stability.challenge_statuses cs
                ON cs.challenge_id = leaf.id AND cs.team_id = :team_id
            WHERE terr2.region_id = :region_id AND terr2.challenge_id IS NOT NULL
            GROUP BY terr2.id
        ) per_terr ON per_terr.territory_id = terr.id
        WHERE terr.region_id = :region_id AND terr.challenge_id IS NOT NULL
    """), {"team_id": str(team_id), "region_id": str(region_id)}).fetchone()

    if not result or int(result.total) == 0 or result.total != result.completed:
        return False

    session.execute(text("""
        UPDATE new_stability.regions
        SET green_logged_teams = array_append(green_logged_teams, CAST(:team_id AS uuid))
        WHERE id = :region_id
    """), {"team_id": str(team_id), "region_id": str(region_id)})

    return True


def recalculate_team_points(team_id, event_id, session) -> int:
    """
    Recompute a team's total points from all four scoring sources and write to teams.points.
    Must be called inside an open transaction; does not commit.
    """
    result = session.execute(text("""
        SELECT
            (
                SELECT COUNT(*)
                FROM new_stability.territories t
                JOIN new_stability.regions r ON r.id = t.region_id
                WHERE r.event_id = :event_id AND t.controlling_team_id = :team_id
            ) AS territories_controlled,
            (
                SELECT COUNT(*)
                FROM new_stability.regions
                WHERE event_id = :event_id AND controlling_team_id = :team_id
            ) AS regions_controlled
    """), {"team_id": str(team_id), "event_id": str(event_id)}).fetchone()

    points = (
        int(result.territories_controlled) * CONQUEST_SCORING["TERRITORY_OWNED"] +
        int(result.regions_controlled) * CONQUEST_SCORING["REGION_OWNED"]
    )

    session.execute(text("""
        UPDATE new_stability.teams SET points = :points, updated_at = NOW() WHERE id = :team_id
    """), {"points": points, "team_id": str(team_id)})

    logging.debug(f"[CONQUEST] team={team_id} points recalculated to {points}")
    return points
