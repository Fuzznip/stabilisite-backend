#!/usr/bin/env python3
"""
Boss of the week test suite.
Run from the project root: PYTHONPATH=. python tests/test_botw.py

Covers:
  - Creating a boss from an explicit drop list (container, KC, one per drop)
  - KC submissions scoring one kill, not the cumulative count Dink sends
  - Drops scoring every time, including duplicates
  - Sourceless triggers matching regardless of the submission's source
  - Adding and removing individual drops
  - Generic field updates on a boss
  - Player-owned statuses staying out of team queries
  - Point values being applied at read time (edit a value, leaderboard moves)
  - Bulk point editing and its ownership guard
  - The whitelist exposing botw drops and boss KC names
  - Unconfigured drops, unknown users, and duplicate request_ids being ignored

Nothing here touches the collection log — drop lists are supplied outright, so
the suite needs no seeded catalog.
"""

import datetime
import json
import sys
import uuid
from datetime import timedelta, timezone

from app import app, db
from event_handlers.botw.botw_event_handler import botw_event_handler
from event_handlers.event_handler import EventSubmission
from models.models import Events as LegacyEvents, Users
from models.new_events import (
    BotwBoss, Challenge, ChallengeStatus, Event, Trigger,
)
from services.botw_service import leaderboard

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_pass = 0
_fail = 0

BOSS = "Duke Sucellus"

# The drop list is stated here rather than read from a catalog page.
DROPS = [
    {"name": "Awakener's orb"},
    {"name": "Chromium ingot"},
    {"name": "Magus vestige", "points": 40},
    {"name": "Virtus mask", "img_path": "https://example.invalid/virtus_mask.png"},
]
DROP_NAMES = sorted(d["name"] for d in DROPS)


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


def _park_other_botw_events(now):
    """Move any other live botw event out of the active window for this run.

    botw_event_handler scores every active botw event, so a real event running
    locally would score the suite's submissions too whenever a trigger name
    overlaps, perturbing the point assertions. Returns the original dates so the
    finally block can put them back exactly.
    """
    parked = []
    others = Event.query.filter(
        Event.type == 'botw',
        Event.start_date <= now,
        Event.end_date >= now,
    ).all()
    for event in others:
        parked.append((event.id, event.start_date, event.end_date))
        event.end_date = now - timedelta(days=1)
    if parked:
        db.session.commit()
        print(f"  Parked {len(parked)} other active botw event(s) for the run.")
    return parked


def _restore_parked_events(parked):
    try:
        for event_id, start_date, end_date in parked:
            event = Event.query.get(event_id)
            if event:
                event.start_date = start_date
                event.end_date = end_date
        db.session.commit()
        if parked:
            print(f"  Restored {len(parked)} parked event(s).")
    except Exception as exc:
        print(f"  ⚠️  FAILED to restore parked events: {exc}")
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

        alice = bob = None
        botw = bingo = botw2 = None
        parked = _park_other_botw_events(now)

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
            # CREATION
            # ================================================================
            print("\n── Creation ────────────────────────────────────────────────")

            resp = client.post(
                f"/v2/events/{botw.id}/botw/bosses",
                json={"name": BOSS, "kc_points": 3, "drop_points": 10, "drops": DROPS},
            )
            check(resp.status_code == 201, "POST boss returns 201", f"got {resp.status_code}: {resp.data[:200]}")
            boss_data = json.loads(resp.data)

            boss = BotwBoss.query.filter_by(event_id=botw.id).first()
            check(boss is not None and boss.challenge_id is not None,
                  "boss row created with a container challenge")

            children = Challenge.query.filter_by(parent_challenge_id=boss.challenge_id).all()
            check(len(children) == len(DROPS) + 1,
                  f"one challenge per supplied drop plus KC ({len(DROPS)} + 1)",
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
            check(sorted(triggers[c.trigger_id].name for c in drop_children) == DROP_NAMES,
                  "drop challenges match the supplied list exactly",
                  f"got {sorted(triggers[c.trigger_id].name for c in drop_children)}")
            check(all(triggers[c.trigger_id].source is None for c in children),
                  "triggers are created without a source")
            check(triggers[kc_children[0].trigger_id].source is None,
                  "the KC trigger has no source either")

            by_name = {triggers[c.trigger_id].name: c for c in drop_children}
            orb_value = by_name["Awakener's orb"].value
            magus_value = by_name["Magus vestige"].value
            check(orb_value == 10,
                  "a drop without points falls back to drop_points",
                  f"got {orb_value}")
            check(magus_value == 40,
                  "a drop with explicit points overrides drop_points",
                  f"got {magus_value}")
            check(triggers[by_name["Virtus mask"].trigger_id].img_path ==
                  "https://example.invalid/virtus_mask.png",
                  "img_path from the payload lands on the trigger")
            check(len(boss_data.get('challenges', [])) == len(children),
                  "response embeds the challenge tree")

            kc_challenge = kc_children[0]
            orb = by_name["Awakener's orb"]
            other_drop = by_name["Chromium ingot"]

            # A boss with no drops at all is a legitimate kills-only week
            resp = client.post(
                f"/v2/events/{botw.id}/botw/bosses",
                json={"name": f"KC Only {uid}", "kc_points": 5},
            )
            check(resp.status_code == 201, "a boss with no drops is accepted",
                  f"got {resp.status_code}: {resp.data[:200]}")
            kc_only = BotwBoss.query.filter_by(event_id=botw.id, name=f"KC Only {uid}").first()
            check(Challenge.query.filter_by(parent_challenge_id=kc_only.challenge_id).count() == 1,
                  "a KC-only boss has exactly one child challenge")

            resp = client.post(
                f"/v2/events/{botw.id}/botw/bosses",
                json={"name": f"Bad {uid}", "drops": "not-a-list"},
            )
            check(resp.status_code == 400, "a non-list drops field returns 400",
                  f"got {resp.status_code}")

            resp = client.post(
                f"/v2/events/{botw.id}/botw/bosses",
                json={"name": f"Bad {uid}", "drops": [{"points": 5}]},
            )
            check(resp.status_code == 400, "a drop without a name returns 400",
                  f"got {resp.status_code}")

            resp = client.post(
                f"/v2/events/{botw.id}/botw/bosses",
                json={"name": f"Bad {uid}", "drops": [{"name": "X", "points": "lots"}]},
            )
            check(resp.status_code == 400, "a non-integer drop value returns 400",
                  f"got {resp.status_code}")

            resp = client.post(f"/v2/events/{bingo.id}/botw/bosses", json={"name": BOSS})
            check(resp.status_code == 400, "creating on a non-botw event returns 400",
                  f"got {resp.status_code}")

            # ================================================================
            # KC SCORING
            # ================================================================
            print("\n── KC scoring ──────────────────────────────────────────────")

            notifications = submit(alice.runescape_name, BOSS, type="KC", quantity=143,
                                   source=BOSS, request_id=f"kc1_{uid}")
            status = status_for(alice.id, kc_challenge.id)
            check(status is not None and status.quantity == 1,
                  "a KC submission of quantity=143 advances progress by 1 kill",
                  f"got {status.quantity if status else None}")
            check(notifications == [], "KC submission scores silently (no channel notification)")
            check(points_for(alice.runescape_name, leaderboard(botw.id)) == 3,
                  "one kill is worth kc_points")

            submit(alice.runescape_name, BOSS, type="KC", quantity=144,
                   source=BOSS, request_id=f"kc2_{uid}")
            check(status_for(alice.id, kc_challenge.id).quantity == 2, "a second kill counts once more")
            check(points_for(alice.runescape_name, leaderboard(botw.id)) == 6, "two kills are worth 6")

            # ================================================================
            # DROP SCORING
            # ================================================================
            print("\n── Drop scoring ────────────────────────────────────────────")

            submit(alice.runescape_name, "Awakener's orb", source=BOSS, request_id=f"orb1_{uid}")
            check(status_for(alice.id, orb.id).quantity == 1, "a drop scores")
            check(points_for(alice.runescape_name, leaderboard(botw.id)) == 16, "6 KC + 10 drop = 16")

            submit(alice.runescape_name, "Awakener's orb", source=BOSS, request_id=f"orb2_{uid}")
            submit(alice.runescape_name, "Awakener's orb", source=BOSS, request_id=f"orb3_{uid}")
            check(status_for(alice.id, orb.id).quantity == 3, "duplicate drops score every time")
            check(points_for(alice.runescape_name, leaderboard(botw.id)) == 36, "three orbs are worth 30")

            # Stacked drops score per item
            submit(bob.runescape_name, "Awakener's orb", source=BOSS, quantity=2,
                   request_id=f"boborb_{uid}")
            check(status_for(bob.id, orb.id).quantity == 2, "a stack of 2 scores twice")

            # Triggers are created sourceless, and the handler treats a null
            # trigger source as matching anything — so the submission's source
            # is irrelevant. This is the whole point of dropping the default.
            # Kept off the orb so it does not disturb the ordering assertions.
            submit(bob.runescape_name, "Chromium ingot", source="Vardorvis",
                   request_id=f"othersrc_{uid}")
            check(status_for(bob.id, other_drop.id).quantity == 1,
                  "a sourceless trigger scores regardless of the submission source",
                  f"got {status_for(bob.id, other_drop.id)}")

            submit(bob.runescape_name, "Chromium ingot", source=None,
                   request_id=f"nosrc_{uid}")
            check(status_for(bob.id, other_drop.id).quantity == 2,
                  "a submission with no source at all still scores",
                  f"got {status_for(bob.id, other_drop.id).quantity}")

            submit(bob.runescape_name, BOSS, type="KC", quantity=10, source=None,
                   request_id=f"nosrckc_{uid}")
            check(status_for(bob.id, kc_challenge.id) is not None,
                  "a KC submission with no source scores (it did not before)")

            # Unconfigured item
            before = len(ChallengeStatus.query.filter_by(player_id=bob.id).all())
            submit(bob.runescape_name, f"Not A Real Item {uid}", source=BOSS,
                   request_id=f"unknown_{uid}")
            check(len(ChallengeStatus.query.filter_by(player_id=bob.id).all()) == before,
                  "an unconfigured drop scores nothing")

            # Unknown player
            notifications = submit(f"GhostPlayer_{uid}", "Awakener's orb", source=BOSS,
                                   request_id=f"ghost_{uid}")
            check(notifications == [], "a submission from an unknown player is ignored")

            # Duplicate request_id
            submit(bob.runescape_name, "Awakener's orb", source=BOSS, quantity=2,
                   request_id=f"boborb_{uid}")
            check(status_for(bob.id, orb.id).quantity == 2,
                  "a replayed request_id does not score twice",
                  f"got {status_for(bob.id, orb.id).quantity}")

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
            check(standings[0]['bosses'][0]['boss_name'] == BOSS, "per-boss breakdown is present")

            resp = client.get(f"/v2/events/{botw.id}/botw/leaderboard")
            check(resp.status_code == 200, "GET leaderboard returns 200")
            check(len(json.loads(resp.data)['data']) == 2, "leaderboard lists both players")

            resp = client.get(f"/v2/events/{bingo.id}/botw/leaderboard")
            check(resp.status_code == 400, "leaderboard on a non-botw event returns 400")

            resp = client.get(f"/v2/events/{botw.id}/botw/bosses")
            check(resp.status_code == 200 and len(json.loads(resp.data)['data']) == 2,
                  "GET bosses returns both configured bosses")

            check(client.get("/v2/botw/catalog/pages").status_code == 404,
                  "the collection log catalog endpoint is gone")

            # ================================================================
            # DROP EDITING
            # ================================================================
            print("\n── Drop editing ────────────────────────────────────────────")

            resp = client.post(
                f"/v2/botw/bosses/{boss.id}/drops",
                json={"name": f"Added Item {uid}", "points": 7},
            )
            check(resp.status_code == 201, "POST drop returns 201", f"got {resp.status_code}")
            added = next(
                c for c in Challenge.query.filter_by(parent_challenge_id=boss.challenge_id).all()
                if Trigger.query.get(c.trigger_id).name == f"Added Item {uid}"
            )
            check(added.value == 7, "the added drop carries its points")

            submit(alice.runescape_name, f"Added Item {uid}", request_id=f"added_{uid}")
            check(status_for(alice.id, added.id).quantity == 1, "a newly added drop scores")

            resp = client.post(f"/v2/botw/bosses/{boss.id}/drops", json={"points": 3})
            check(resp.status_code == 400, "adding a drop without a name returns 400",
                  f"got {resp.status_code}")

            # Removing a drop takes its statuses with it, but nothing else.
            # Hold the id, not the instance: touching an attribute on a deleted
            # ORM object raises ObjectDeletedError rather than returning None.
            added_id = added.id
            orb_before = status_for(alice.id, orb.id).quantity
            resp = client.delete(f"/v2/botw/drops/{added_id}")
            check(resp.status_code == 200, "DELETE drop returns 200", f"got {resp.status_code}")
            db.session.expire_all()
            check(Challenge.query.filter_by(id=added_id).first() is None,
                  "the drop challenge is gone")
            check(ChallengeStatus.query.filter_by(challenge_id=added_id).count() == 0,
                  "its statuses cascade away")
            check(status_for(alice.id, orb.id).quantity == orb_before,
                  "the other drops keep their progress")

            check(client.delete(f"/v2/botw/drops/{uuid.uuid4()}").status_code == 404,
                  "deleting an unknown drop returns 404")
            check(client.delete(f"/v2/botw/drops/{boss.challenge_id}").status_code == 404,
                  "the container challenge is not deletable through the drop route")

            # ================================================================
            # GENERIC BOSS UPDATE
            # ================================================================
            print("\n── Boss update ─────────────────────────────────────────────")

            resp = client.put(
                f"/v2/botw/bosses/{boss.id}",
                json={"name": f"Renamed {uid}", "display_order": 9,
                      "image_url": "https://example.invalid/boss.png"},
            )
            check(resp.status_code == 200, "PUT boss returns 200", f"got {resp.status_code}")
            db.session.expire_all()
            refreshed = BotwBoss.query.get(boss.id)
            check(refreshed.name == f"Renamed {uid}", "name is updated")
            check(refreshed.display_order == 9, "display_order is updated")
            check(refreshed.image_url == "https://example.invalid/boss.png", "image_url is updated")

            check(client.put(f"/v2/botw/bosses/{uuid.uuid4()}", json={"name": "x"}).status_code == 404,
                  "PUT on an unknown boss returns 404")

            # ================================================================
            # OVERLAPPING EVENTS
            # ================================================================
            print("\n── Overlapping events ──────────────────────────────────────")

            # A second live botw event. The handler used to resolve the event
            # with .first(), so whichever row came back swallowed every
            # submission and this one would score nothing.
            botw2 = Event(
                name=f"Test BOTW second {uid}",
                type="botw",
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(days=7),
            )
            db.session.add(botw2)
            db.session.commit()

            resp = client.post(
                f"/v2/events/{botw2.id}/botw/bosses",
                json={"name": f"Second Boss {uid}", "drop_points": 5,
                      "drops": [{"name": "Awakener's orb"}]},
            )
            check(resp.status_code == 201, "second event's boss is created",
                  f"got {resp.status_code}")

            boss2 = BotwBoss.query.filter_by(event_id=botw2.id).first()
            orb2 = Challenge.query.filter_by(parent_challenge_id=boss2.challenge_id).filter(
                Challenge.trigger_id.isnot(None)
            ).all()
            orb2 = next(c for c in orb2 if Trigger.query.get(c.trigger_id).name == "Awakener's orb")

            orb1_before = status_for(bob.id, orb.id).quantity

            notifications = submit(bob.runescape_name, "Awakener's orb",
                                   request_id=f"overlap_{uid}")
            check(len(notifications) == 2,
                  "one submission notifies both active events",
                  f"got {len(notifications)}")
            check(status_for(bob.id, orb.id).quantity == orb1_before + 1,
                  "it scores in the first event",
                  f"got {status_for(bob.id, orb.id).quantity}")
            check(status_for(bob.id, orb2.id) is not None
                  and status_for(bob.id, orb2.id).quantity == 1,
                  "and in the second event too")
            check(points_for(bob.runescape_name, leaderboard(botw2.id)) == 5,
                  "the second event scores it at its own point value",
                  f"got {points_for(bob.runescape_name, leaderboard(botw2.id))}")

            # The dedupe guard is per event, so a replay is still refused
            submit(bob.runescape_name, "Awakener's orb", request_id=f"overlap_{uid}")
            check(status_for(bob.id, orb2.id).quantity == 1,
                  "a replayed request_id is still refused per event",
                  f"got {status_for(bob.id, orb2.id).quantity}")

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
            check(BOSS in whitelist['killCountTriggers'],
                  "boss KC name reaches killCountTriggers")
            # Sourceless triggers are whitelisted bare, with no ":source" suffix.
            check("awakener's orb" in [t.lower() for t in whitelist['triggers']],
                  "boss drops reach the drop whitelist without a source suffix",
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
            _cleanup([botw, bingo, botw2], [alice, bob])
            _restore_parked_events(parked)

        print("\n" + "=" * 70)
        print(f"  RESULTS: {_pass} passed, {_fail} failed")
        print("=" * 70 + "\n")
        return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(run())
