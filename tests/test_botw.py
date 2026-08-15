#!/usr/bin/env python3
"""
Boss of the week test suite.
Run from the project root: PYTHONPATH=. python tests/test_botw.py

Covers:
  - Seeding a boss from the collection log catalog (container, KC, one per drop)
  - KC submissions scoring one kill, not the cumulative count Dink sends
  - Drops scoring every time, including duplicates
  - Player-owned statuses staying out of team queries
  - Point values being applied at read time (edit a value, leaderboard moves)
  - Bulk point editing and its ownership guard
  - The whitelist exposing botw drops and boss KC names
  - Unconfigured drops, unknown users, and duplicate request_ids being ignored
"""

import datetime
import json
import sys
import uuid
from datetime import timedelta, timezone

from app import app, db
from event_handlers.botw.botw_event_handler import botw_event_handler
from event_handlers.event_handler import EventSubmission
from models.models import CollectionLogItem, Events as LegacyEvents, Users
from models.new_events import (
    BotwBoss, Challenge, ChallengeStatus, Event, Trigger,
)
from services.botw_service import leaderboard

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_pass = 0
_fail = 0

PAGE = "Duke Sucellus"   # 10 catalog items, stable page name


def check(condition, name, detail=""):
    global _pass, _fail
    if condition:
        _pass += 1
        print(f"  ✅  {name}")
    else:
        _fail += 1
        print(f"  ❌  {name}")
        if detail:
            print(f"       → {detail}")
    return condition


def submit(rsn, trigger_name, *, type="DROP", quantity=1, source=None, request_id=None):
    return botw_event_handler(EventSubmission(
        rsn=rsn,
        id=None,
        trigger=trigger_name,
        source=source,
        quantity=quantity,
        totalValue=None,
        img_path=None,
        type=type,
        request_id=request_id,
    ))


def status_for(player_id, challenge_id):
    db.session.expire_all()
    return ChallengeStatus.query.filter_by(player_id=player_id, challenge_id=challenge_id).first()


def points_for(rsn, standings):
    for row in standings:
        if row['rsn'] == rsn:
            return row['points']
    return None


def _purge_stale_test_data():
    """Remove leftovers from a crashed run. Only matches test-created objects."""
    try:
        stale_events = Event.query.filter(Event.name.like("Test BOTW %")).all()
        for e in stale_events:
            for boss in BotwBoss.query.filter_by(event_id=e.id).all():
                container_id = boss.challenge_id
                db.session.delete(boss)
                db.session.flush()
                if container_id:
                    # Bulk delete so children are removed rather than orphaned.
                    Challenge.query.filter_by(parent_challenge_id=container_id).delete(synchronize_session=False)
                    Challenge.query.filter_by(id=container_id).delete(synchronize_session=False)
            db.session.delete(e)
        db.session.flush()

        stale_users = Users.query.filter(Users.discord_id.like("botw_%")).all()
        for u in stale_users:
            db.session.delete(u)
        db.session.commit()
    except Exception as exc:
        print(f"  [pre-cleanup warning: {exc}]")
        db.session.rollback()


def _cleanup(events, users):
    try:
        db.session.rollback()
        for e in events:
            obj = Event.query.get(e.id) if e else None
            if not obj:
                continue
            for boss in BotwBoss.query.filter_by(event_id=obj.id).all():
                container_id = boss.challenge_id
                db.session.delete(boss)
                db.session.flush()
                if container_id:
                    # Bulk delete so children are removed rather than orphaned.
                    Challenge.query.filter_by(parent_challenge_id=container_id).delete(synchronize_session=False)
                    Challenge.query.filter_by(id=container_id).delete(synchronize_session=False)
            db.session.delete(obj)
        db.session.flush()
        for u in users:
            obj = Users.query.get(u.id) if u else None
            if obj:
                db.session.delete(obj)
        db.session.commit()
        print("  Cleanup done.")
    except Exception as exc:
        print(f"  Cleanup error (ignored): {exc}")
        db.session.rollback()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    with app.app_context():
        client = app.test_client()

        print("\n" + "=" * 70)
        print("  BOSS OF THE WEEK TEST SUITE")
        print("=" * 70)

        now = datetime.datetime.now(timezone.utc)
        uid = uuid.uuid4().hex[:8]

        print("\n── Pre-cleanup (stale data from previous runs) ──────────────")
        _purge_stale_test_data()

        catalog_items = CollectionLogItem.query.filter_by(page=PAGE).all()
        if not catalog_items:
            print(f"\n  ⚠️  collection_log_items has no rows for {PAGE!r}.")
            print("      Seed it first: PYTHONPATH=. python scripts/seed_collection_log.py")
            return 1
        item_names = sorted(i.name for i in catalog_items)

        alice = bob = None
        botw = bingo = None

        try:
            # ================================================================
            # SETUP
            # ================================================================
            print("\n── Setup ───────────────────────────────────────────────────")

            alice = Users(discord_id=f"botw_alice_{uid}", runescape_name=f"Alice_{uid}")
            bob = Users(discord_id=f"botw_bob_{uid}", runescape_name=f"Bob_{uid}")
            db.session.add_all([alice, bob])
            db.session.flush()

            botw = Event(
                name=f"Test BOTW {uid}",
                type="botw",
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(days=7),
            )
            # Non-botw event, used to verify the endpoint type guard
            bingo = Event(
                name=f"Test BOTW guard {uid}",
                type="bingo",
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(days=7),
            )
            db.session.add_all([botw, bingo])
            db.session.commit()
            print(f"  Event {botw.name} ({botw.id})")

            # ================================================================
            # SEEDING
            # ================================================================
            print("\n── Seeding ─────────────────────────────────────────────────")

            resp = client.post(
                f"/v2/events/{botw.id}/botw/bosses",
                json={"name": PAGE, "kc_points": 3, "drop_points": 10},
            )
            check(resp.status_code == 201, "POST boss returns 201", f"got {resp.status_code}: {resp.data[:200]}")
            boss_data = json.loads(resp.data)

            boss = BotwBoss.query.filter_by(event_id=botw.id).first()
            check(boss is not None and boss.challenge_id is not None,
                  "boss row created with a container challenge")

            children = Challenge.query.filter_by(parent_challenge_id=boss.challenge_id).all()
            check(len(children) == len(catalog_items) + 1,
                  f"one challenge per drop plus KC ({len(catalog_items)} + 1)",
                  f"got {len(children)}")

            triggers = {t.id: t for t in Trigger.query.filter(
                Trigger.id.in_([c.trigger_id for c in children])
            ).all()}
            kc_children = [c for c in children if triggers[c.trigger_id].type == 'KC']
            drop_children = [c for c in children if triggers[c.trigger_id].type == 'DROP']

            check(len(kc_children) == 1, "exactly one KC challenge")
            check(kc_children[0].count_per_action == 1,
                  "KC challenge sets count_per_action=1 (Dink sends cumulative KC)",
                  f"got {kc_children[0].count_per_action}")
            check(kc_children[0].value == 3, "KC challenge carries kc_points")
            check(all(c.quantity is None for c in children),
                  "every challenge is repeatable (quantity NULL)")
            check(sorted(triggers[c.trigger_id].name for c in drop_children) == item_names,
                  "drop challenges match the catalog page exactly")
            check(all(triggers[c.trigger_id].wiki_id is not None for c in drop_children),
                  "drop triggers carry the OSRS item id for icons")
            check(all(c.value == 10 for c in drop_children), "drop challenges carry drop_points")
            check(len(boss_data.get('challenges', [])) == len(children),
                  "response embeds the challenge tree")

            kc_challenge = kc_children[0]
            orb = next(c for c in drop_children if triggers[c.trigger_id].name == "Awakener's orb")
            other_drop = next(c for c in drop_children if c.id != orb.id)

            # Seeding a page with no catalog rows is rejected
            resp = client.post(
                f"/v2/events/{botw.id}/botw/bosses",
                json={"name": f"Nonexistent Boss {uid}"},
            )
            check(resp.status_code == 400, "seeding an unknown clog page returns 400",
                  f"got {resp.status_code}")

            resp = client.post(f"/v2/events/{bingo.id}/botw/bosses", json={"name": PAGE})
            check(resp.status_code == 400, "seeding a non-botw event returns 400",
                  f"got {resp.status_code}")

            # ================================================================
            # KC SCORING
            # ================================================================
            print("\n── KC scoring ──────────────────────────────────────────────")

            notifications = submit(alice.runescape_name, PAGE, type="KC", quantity=143,
                                   source=PAGE, request_id=f"kc1_{uid}")
            status = status_for(alice.id, kc_challenge.id)
            check(status is not None and status.quantity == 1,
                  "a KC submission of quantity=143 advances progress by 1 kill",
                  f"got {status.quantity if status else None}")
            check(len(notifications) == 1, "KC submission produces a notification")
            check(points_for(alice.runescape_name, leaderboard(botw.id)) == 3,
                  "one kill is worth kc_points")

            submit(alice.runescape_name, PAGE, type="KC", quantity=144,
                   source=PAGE, request_id=f"kc2_{uid}")
            check(status_for(alice.id, kc_challenge.id).quantity == 2, "a second kill counts once more")
            check(points_for(alice.runescape_name, leaderboard(botw.id)) == 6, "two kills are worth 6")

            # ================================================================
            # DROP SCORING
            # ================================================================
            print("\n── Drop scoring ────────────────────────────────────────────")

            submit(alice.runescape_name, "Awakener's orb", source=PAGE, request_id=f"orb1_{uid}")
            check(status_for(alice.id, orb.id).quantity == 1, "a drop scores")
            check(points_for(alice.runescape_name, leaderboard(botw.id)) == 16, "6 KC + 10 drop = 16")

            submit(alice.runescape_name, "Awakener's orb", source=PAGE, request_id=f"orb2_{uid}")
            submit(alice.runescape_name, "Awakener's orb", source=PAGE, request_id=f"orb3_{uid}")
            check(status_for(alice.id, orb.id).quantity == 3, "duplicate drops score every time")
            check(points_for(alice.runescape_name, leaderboard(botw.id)) == 36, "three orbs are worth 30")

            # Stacked drops score per item
            submit(bob.runescape_name, "Awakener's orb", source=PAGE, quantity=2,
                   request_id=f"boborb_{uid}")
            check(status_for(bob.id, orb.id).quantity == 2, "a stack of 2 scores twice")

            # Wrong source is not this boss's drop
            submit(bob.runescape_name, "Awakener's orb", source="Vardorvis",
                   request_id=f"wrongsrc_{uid}")
            check(status_for(bob.id, orb.id).quantity == 2, "a drop from another source is ignored")

            # Unconfigured item
            before = len(ChallengeStatus.query.filter_by(player_id=bob.id).all())
            submit(bob.runescape_name, f"Not A Real Item {uid}", source=PAGE,
                   request_id=f"unknown_{uid}")
            check(len(ChallengeStatus.query.filter_by(player_id=bob.id).all()) == before,
                  "an unconfigured drop scores nothing")

            # Unknown player
            notifications = submit(f"GhostPlayer_{uid}", "Awakener's orb", source=PAGE,
                                   request_id=f"ghost_{uid}")
            check(notifications == [], "a submission from an unknown player is ignored")

            # Duplicate request_id
            submit(bob.runescape_name, "Awakener's orb", source=PAGE, quantity=2,
                   request_id=f"boborb_{uid}")
            check(status_for(bob.id, orb.id).quantity == 2,
                  "a replayed request_id does not score twice")

            # ================================================================
            # OWNERSHIP ISOLATION
            # ================================================================
            print("\n── Ownership isolation ─────────────────────────────────────")

            player_rows = ChallengeStatus.query.filter_by(player_id=alice.id).all()
            check(all(r.team_id is None for r in player_rows),
                  "player-owned statuses have no team")
            check(ChallengeStatus.query.filter_by(team_id=None).filter(
                      ChallengeStatus.player_id.is_(None)).count() == 0,
                  "no status row is left ownerless")

            team_query_rows = ChallengeStatus.query.filter(
                ChallengeStatus.challenge_id.in_([orb.id, kc_challenge.id]),
                ChallengeStatus.team_id.isnot(None),
            ).count()
            check(team_query_rows == 0, "team-scoped queries do not see player rows")

            # ================================================================
            # POINT EDITING
            # ================================================================
            print("\n── Point editing ───────────────────────────────────────────")

            resp = client.put(
                f"/v2/botw/bosses/{boss.id}/points",
                json={"points": {str(orb.id): 25}},
            )
            check(resp.status_code == 200, "bulk point edit returns 200", f"got {resp.status_code}")
            check(points_for(alice.runescape_name, leaderboard(botw.id)) == 81,
                  "editing a value rescales points already earned (6 + 3×25)",
                  f"got {points_for(alice.runescape_name, leaderboard(botw.id))}")

            resp = client.put(
                f"/v2/botw/bosses/{boss.id}/points",
                json={"points": {str(uuid.uuid4()): 5}},
            )
            check(resp.status_code == 400, "editing a challenge from another boss returns 400",
                  f"got {resp.status_code}")

            # ================================================================
            # LEADERBOARD
            # ================================================================
            print("\n── Leaderboard ─────────────────────────────────────────────")

            standings = leaderboard(botw.id)
            check([s['rsn'] for s in standings][:2] == [alice.runescape_name, bob.runescape_name],
                  "standings are ordered by points descending",
                  f"got {[(s['rsn'], s['points']) for s in standings]}")
            check(standings[0]['rank'] == 1 and standings[1]['rank'] == 2, "ranks are assigned")
            check(standings[0]['bosses'][0]['boss_name'] == PAGE, "per-boss breakdown is present")

            resp = client.get(f"/v2/events/{botw.id}/botw/leaderboard")
            check(resp.status_code == 200, "GET leaderboard returns 200")
            check(len(json.loads(resp.data)['data']) == 2, "leaderboard lists both players")

            resp = client.get(f"/v2/events/{bingo.id}/botw/leaderboard")
            check(resp.status_code == 400, "leaderboard on a non-botw event returns 400")

            resp = client.get(f"/v2/events/{botw.id}/botw/bosses")
            check(resp.status_code == 200 and len(json.loads(resp.data)['data']) == 1,
                  "GET bosses returns the configured boss")

            resp = client.get("/v2/botw/catalog/pages?category=Bosses")
            pages = json.loads(resp.data)['data']
            check(resp.status_code == 200 and any(p['page'] == PAGE for p in pages),
                  "catalog pages endpoint lists boss pages")

            # ================================================================
            # WHITELIST
            # ================================================================
            print("\n── Whitelist ───────────────────────────────────────────────")

            # /events/whitelist reads the legacy public.events table before the
            # new-schema paths. It exists everywhere the app is deployed, but a
            # dev database created from the new_stability migrations alone may
            # not have it, and its absence 500s the endpoint. No-op if present.
            LegacyEvents.__table__.create(db.engine, checkfirst=True)

            resp = client.get("/events/whitelist")
            check(resp.status_code == 200, "GET whitelist returns 200",
                  f"got {resp.status_code}: {resp.data[:200]}")
            whitelist = json.loads(resp.data)
            check(PAGE in whitelist['killCountTriggers'],
                  "boss KC name reaches killCountTriggers")
            check(f"awakener's orb:{PAGE.lower()}" in [t.lower() for t in whitelist['triggers']],
                  "boss drops reach the drop whitelist",
                  f"got {[t for t in whitelist['triggers'] if 'orb' in t.lower()][:5]}")

            # ================================================================
            # DELETION
            # ================================================================
            print("\n── Deletion ────────────────────────────────────────────────")

            container_id = boss.challenge_id
            child_ids = [c.id for c in Challenge.query.filter_by(parent_challenge_id=container_id).all()]
            resp = client.delete(f"/v2/botw/bosses/{boss.id}")
            check(resp.status_code == 200, "DELETE boss returns 200", f"got {resp.status_code}")
            check(BotwBoss.query.get(boss.id) is None, "boss row is gone")
            # By id, not by parent link: orphaned children would still pass a
            # parent-link check while sitting in the table forever.
            check(Challenge.query.filter(Challenge.id.in_(child_ids + [container_id])).count() == 0,
                  "its challenges are deleted, not orphaned")
            check(ChallengeStatus.query.filter_by(player_id=alice.id).count() == 0,
                  "player statuses cascade away with the challenges")

        finally:
            print("\n── Cleanup ─────────────────────────────────────────────────")
            _cleanup([botw, bingo], [alice, bob])

        print("\n" + "=" * 70)
        print(f"  RESULTS: {_pass} passed, {_fail} failed")
        print("=" * 70 + "\n")
        return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(run())
