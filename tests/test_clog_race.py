#!/usr/bin/env python3
"""
Collection log race test suite.
Run from the project root: PYTHONPATH=. .venv/bin/python tests/test_clog_race.py

Covers:
  - Generating slots from the catalog: dedupe on item_id, point tiers
  - Trigger reuse: an existing sourceless trigger is reused, a sourced one is not
  - Scoring: first drop completes, duplicates score nothing, teams don't block
  - Null thread_id suppressing notifications without affecting scoring
  - Points applied at read time
  - The whitelist exposing clog slot names
  - Re-run isolation: a second event leaves the first event's statuses alone
"""

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone

from app import app, db
from event_handlers.event_handler import EventSubmission
from event_handlers.collection_log_race.handler import collection_log_race_handler
from models.models import CollectionLogItem, Users
from models.new_events import (
    Challenge, ChallengeProof, ChallengeStatus, ClogSlot, Event, Team, TeamMember, Trigger,
)
from services import clog_service
from services.challenge_evaluator import ChallengeEvaluator

_pass = 0
_fail = 0

# A miniature catalog. Dragon pickaxe is deliberately on two Bosses pages, so
# dedupe has something to collapse; Twisted bow is Raids and Oathplate helm is
# Yama, so both 3-point rules have a case.
CATALOG = [
    dict(item_id=11920, name="Dragon pickaxe", category="Bosses", page="Callisto and Artio", page_order=5, sequence=2),
    dict(item_id=11920, name="Dragon pickaxe", category="Bosses", page="King Black Dragon", page_order=2, sequence=1),
    dict(item_id=12922, name="Tanzanite fang", category="Bosses", page="Zulrah", page_order=9, sequence=0),
    dict(item_id=30750, name="Oathplate helm", category="Bosses", page="Yama", page_order=8, sequence=0),
    dict(item_id=20997, name="Twisted bow", category="Raids", page="Chambers of Xeric", page_order=1, sequence=0),
    dict(item_id=4151, name="Abyssal whip", category="Other", page="Slayer", page_order=1, sequence=0),
]


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


def seed_catalog():
    """Install the miniature catalog, replacing whatever is there.

    NOTE: this replaces the real catalog in whatever database the suite points
    at, and _cleanup empties the table afterwards. Restore it with
    `PYTHONPATH=. .venv/bin/python scripts/seed_collection_log.py` before using that
    database for anything else.
    """
    CollectionLogItem.__table__.create(db.engine, checkfirst=True)
    db.session.query(CollectionLogItem).delete()
    db.session.bulk_insert_mappings(CollectionLogItem, CATALOG)
    db.session.commit()


def make_event(name, *, thread_id="thread-1", days_ago=1, days_left=1):
    now = datetime.now(timezone.utc)
    event = Event(
        name=name,
        type='clog',
        thread_id=thread_id,
        start_date=now - timedelta(days=days_ago),
        end_date=now + timedelta(days=days_left),
    )
    db.session.add(event)
    db.session.commit()
    return event


def make_user(rsn, discord_id):
    user = Users(id=uuid.uuid4(), discord_id=discord_id, runescape_name=rsn,
                 is_member=True, is_active=True, rank='Member')
    db.session.add(user)
    db.session.commit()
    return user


def make_team(event, name, members):
    team = Team(event_id=event.id, name=name, points=0)
    db.session.add(team)
    db.session.flush()
    for user in members:
        db.session.add(TeamMember(team_id=team.id, user_id=user.id))
    db.session.commit()
    return team


def submit(rsn, trigger_name, *, type="LOOT", quantity=1, source=None, request_id=None):
    return collection_log_race_handler(EventSubmission(
        rsn=rsn, id=None, trigger=trigger_name, source=source, quantity=quantity,
        totalValue=None, img_path="https://example.invalid/shot.png", type=type,
        request_id=request_id or str(uuid.uuid4()),
    ))


def team_points(event_id, team_id):
    for row in clog_service.progress(event_id)['standings']:
        if row['team_id'] == str(team_id):
            return row['points']
    return None


def run():
    with app.app_context():
        events, users = [], []
        try:
            seed_catalog()

            print("\n── Generation ──────────────────────────────────────────────")
            event = make_event("Test CLOG generation")
            events.append(event)

            slots = clog_service.build_slots(event.id)

            check(len(slots) == 4, "only Bosses and Raids items become slots, deduped",
                  f"got {len(slots)}: {sorted(s.name for s in slots)}")
            check(all(s.category in ('Bosses', 'Raids') for s in slots),
                  "no Other-tab item leaks in")

            by_item = {s.item_id: s for s in slots}
            check(11920 in by_item, "the multi-page item produced exactly one slot")
            check(by_item[11920].page == "King Black Dragon",
                  "its display home is the first placement by (page_order, sequence)",
                  f"got {by_item[11920].page!r}")

            points = {
                s.item_id: Challenge.query.get(s.challenge_id).value
                for s in slots
            }
            check(points[20997] == 3, "raids items are worth 3", f"got {points[20997]}")
            check(points[30750] == 3, "Yama items are worth 3", f"got {points[30750]}")
            check(points[12922] == 1, "other boss items are worth 1", f"got {points[12922]}")
            check(points[11920] == 1, "a deduped boss item is worth 1", f"got {points[11920]}")

            challenges = [Challenge.query.get(s.challenge_id) for s in slots]
            check(all(c.quantity == 1 for c in challenges),
                  "every slot challenge completes on the first drop")
            check(all(c.task_id is None and c.parent_challenge_id is None for c in challenges),
                  "slot challenges are flat leaves, not part of a tile tree")
            check(all(c.trigger_id is not None for c in challenges),
                  "every slot challenge has a trigger")

            print("\n── Trigger reuse ───────────────────────────────────────────")
            tbow_challenge = Challenge.query.get(by_item[20997].challenge_id)
            tbow_trigger = Trigger.query.get(tbow_challenge.trigger_id)
            check(tbow_trigger.source is None,
                  "slot triggers are sourceless so any source scores",
                  f"got {tbow_trigger.source!r}")

            event2 = make_event("Test CLOG generation second run")
            events.append(event2)
            before = Trigger.query.count()
            slots2 = clog_service.build_slots(event2.id)
            after = Trigger.query.count()
            check(after == before, "a second event creates no new triggers",
                  f"{before} → {after}")
            check(len({s.challenge_id for s in slots} & {s.challenge_id for s in slots2}) == 0,
                  "but it does create its own challenges")

            print("\n── Scoring ─────────────────────────────────────────────────")
            scoring = make_event("Test CLOG scoring")
            events.append(scoring)
            clog_service.build_slots(scoring.id)

            alice = make_user("Clog Alice", "clog_alice")
            bob = make_user("Clog Bob", "clog_bob")
            carol = make_user("Clog Carol", "clog_carol")
            nomad = make_user("Clog Nomad", "clog_nomad")
            users.extend([alice, bob, carol, nomad])

            red = make_team(scoring, "Red", [alice, bob])
            blue = make_team(scoring, "Blue", [carol])

            notes = submit("Clog Alice", "Twisted bow", source="Chambers of Xeric")
            check(len(notes) == 1, "a first drop produces one notification", f"got {len(notes)}")
            check(team_points(scoring.id, red.id) == 3, "raids drop scores 3 for the team",
                  f"got {team_points(scoring.id, red.id)}")

            notes = submit("Clog Bob", "Twisted bow", source="Chambers of Xeric")
            check(notes == [], "a teammate's duplicate produces no notification", f"got {notes}")
            check(team_points(scoring.id, red.id) == 3, "and scores nothing",
                  f"got {team_points(scoring.id, red.id)}")

            tbow_slot = ClogSlot.query.filter_by(event_id=scoring.id, item_id=20997).first()
            proofs = (
                ChallengeProof.query
                .join(ChallengeStatus, ChallengeStatus.id == ChallengeProof.challenge_status_id)
                .filter(ChallengeStatus.challenge_id == tbow_slot.challenge_id)
                .count()
            )
            check(proofs == 1, "the duplicate adds no proof row", f"got {proofs}")

            red_tbow_status = ChallengeStatus.query.filter_by(
                team_id=red.id, challenge_id=tbow_slot.challenge_id,
            ).first()
            check(red_tbow_status.quantity == 1, "and does not bump quantity",
                  f"got {red_tbow_status.quantity}")

            notes = submit("Clog Carol", "Twisted bow", source="Chambers of Xeric")
            check(len(notes) == 1, "another team can still complete the same slot")
            check(team_points(scoring.id, blue.id) == 3, "and scores it in full",
                  f"got {team_points(scoring.id, blue.id)}")

            check(submit("Clog Nomad", "Tanzanite fang", source="Zulrah") == [],
                  "a player with no team scores nothing")
            check(submit("Clog Alice", "Abyssal whip", source="Abyssal demon") == [],
                  "an item outside the event scores nothing")
            check(submit("Clog Alice", "Zulrah", type="KC", quantity=50) == [],
                  "a KC submission scores nothing")

            # Sourceless triggers must match whatever source Dink reports.
            check(len(submit("Clog Alice", "Oathplate helm", source="Yama")) == 1,
                  "a Yama drop scores")
            check(team_points(scoring.id, red.id) == 6, "and is worth 3",
                  f"got {team_points(scoring.id, red.id)}")

            print("\n── Points at read time ─────────────────────────────────────")
            fang_slot = ClogSlot.query.filter_by(event_id=scoring.id, item_id=12922).first()
            submit("Clog Alice", "Tanzanite fang", source="Zulrah")
            check(team_points(scoring.id, red.id) == 7, "a 1pt drop adds 1",
                  f"got {team_points(scoring.id, red.id)}")
            fang_challenge = Challenge.query.get(fang_slot.challenge_id)
            fang_challenge.value = 10
            db.session.commit()
            check(team_points(scoring.id, red.id) == 16,
                  "re-valuing a slot moves points already earned",
                  f"got {team_points(scoring.id, red.id)}")

            print("\n── Replay and overlap ──────────────────────────────────────")
            # Blue has not yet completed Oathplate helm (item_id 30750) or
            # Tanzanite fang (item_id 12922). Score the first under an explicit
            # request_id, then replay that SAME request_id against a different
            # item name — this exercises resolve_action's replay detection
            # itself, rather than the earlier "already completed" short-circuit.
            replay_id = str(uuid.uuid4())
            notes = submit("Clog Carol", "Oathplate helm", source="Yama", request_id=replay_id)
            check(len(notes) == 1, "the first submission under a fresh request_id scores")
            after_first = team_points(scoring.id, blue.id)

            notes = submit("Clog Carol", "Tanzanite fang", source="Zulrah", request_id=replay_id)
            check(notes == [], "replaying the same request_id against a different item scores nothing")
            check(team_points(scoring.id, blue.id) == after_first,
                  "request_id replay does not double-score",
                  f"{after_first} → {team_points(scoring.id, blue.id)}")

            blue_fang_slot = ClogSlot.query.filter_by(event_id=scoring.id, item_id=12922).first()
            blue_fang_proofs = (
                ChallengeProof.query
                .join(ChallengeStatus, ChallengeStatus.id == ChallengeProof.challenge_status_id)
                .filter(
                    ChallengeStatus.challenge_id == blue_fang_slot.challenge_id,
                    ChallengeStatus.team_id == blue.id,
                )
                .count()
            )
            check(blue_fang_proofs == 0, "and writes no proof row for the replayed item",
                  f"got {blue_fang_proofs}")

            print("\n── Null thread ─────────────────────────────────────────────")
            quiet = make_event("Test CLOG quiet", thread_id=None)
            events.append(quiet)
            clog_service.build_slots(quiet.id)
            quiet_team = make_team(quiet, "Quiet", [nomad])
            check(submit("Clog Nomad", "Tanzanite fang", source="Zulrah") == [],
                  "a null thread_id emits no notification")
            check(team_points(quiet.id, quiet_team.id) == 1,
                  "but the drop still scores",
                  f"got {team_points(quiet.id, quiet_team.id)}")

            print("\n── Whitelist ───────────────────────────────────────────────")
            with app.test_client() as client:
                resp = client.get("/events/whitelist")
                check(resp.status_code == 200, "GET whitelist returns 200",
                      f"got {resp.status_code}: {resp.data[:200]}")
                whitelist = json.loads(resp.data)
                names = [t.lower() for t in whitelist['triggers']]
                check("twisted bow" in names,
                      "clog slot names reach the drop whitelist bare, with no source suffix",
                      f"got {[n for n in names if 'twisted' in n][:5]}")
                check("oathplate helm" in names, "every slot is whitelisted, not just raids")
                check("abyssal whip" not in names,
                      "an item outside the event is not whitelisted")

                print("\n── Endpoints ───────────────────────────────────────────────")
                resp = client.get(f"/v2/events/{scoring.id}/clog/slots")
                check(resp.status_code == 200, "GET slots returns 200", f"got {resp.status_code}")
                payload = json.loads(resp.data)
                check(len(payload['data']) == 4, "every slot is returned",
                      f"got {len(payload['data'])}")
                # 1 (pickaxe) + 10 (fang, re-valued above) + 3 (helm) + 3 (tbow)
                check(payload['total_points'] == 17,
                      "total_points sums the event's slot values as they stand now",
                      f"got {payload['total_points']}")

                resp = client.get(f"/v2/events/{scoring.id}/clog/progress")
                check(resp.status_code == 200, "GET progress returns 200", f"got {resp.status_code}")
                prog = json.loads(resp.data)
                check(prog['standings'][0]['name'] == "Red",
                      "standings lead with the team on the most points",
                      f"got {prog['standings'][0]}")
                check("20997" in prog['completed'][str(red.id)],
                      "the completed map is keyed by team then item id")

                resp = client.get(f"/v2/events/{event.id}/clog/progress")
                check(resp.status_code == 200, "a clog event with no teams still serves progress")
                no_team_prog = json.loads(resp.data)
                check(no_team_prog['standings'] == [],
                      "and its standings are empty",
                      f"got {no_team_prog['standings']}")

                bingo_event = Event(name="Test CLOG wrong type", type='bingo',
                                    start_date=scoring.start_date, end_date=scoring.end_date)
                db.session.add(bingo_event)
                db.session.commit()
                events.append(bingo_event)
                resp = client.get(f"/v2/events/{bingo_event.id}/clog/slots")
                check(resp.status_code == 400, "a non-clog event is rejected",
                      f"got {resp.status_code}")

                helm_slot = ClogSlot.query.filter_by(event_id=scoring.id, item_id=30750).first()
                helm_slot_id = str(helm_slot.id)
                # Captured now: after the delete the slot row is gone and this id
                # is the only way to prove the challenge went with it.
                helm_challenge_id = helm_slot.challenge_id

                resp = client.put(f"/v2/clog/slots/{helm_slot_id}", json={"points": 7})
                check(resp.status_code == 200, "PUT slot points returns 200", f"got {resp.status_code}")
                check(Challenge.query.get(helm_challenge_id).value == 7,
                      "and writes Challenge.value",
                      f"got {Challenge.query.get(helm_challenge_id).value}")

                resp = client.put(f"/v2/clog/slots/{helm_slot_id}", json={"points": "lots"})
                check(resp.status_code == 400, "a non-integer point value is rejected",
                      f"got {resp.status_code}")

                # Red and Blue both completed this slot earlier, so there are
                # statuses to cascade.
                before = ChallengeStatus.query.filter_by(challenge_id=helm_challenge_id).count()
                check(before > 0, "the slot has statuses before deletion", f"got {before}")

                resp = client.delete(f"/v2/clog/slots/{helm_slot_id}")
                check(resp.status_code == 200, "DELETE slot returns 200", f"got {resp.status_code}")
                check(ClogSlot.query.get(helm_slot_id) is None, "the slot row is gone")
                check(Challenge.query.get(helm_challenge_id) is None,
                      "its challenge is deleted, not orphaned")
                check(ChallengeStatus.query.filter_by(challenge_id=helm_challenge_id).count() == 0,
                      "its statuses cascade away with the challenge")

                print("\n── Generate endpoint ────────────────────────────────────────")
                # Fresh event with no slots yet: don't call build_slots ourselves,
                # the point is to let the endpoint do it.
                generated = make_event("Test CLOG generate endpoint")
                events.append(generated)

                resp = client.post(f"/v2/events/{generated.id}/clog/generate")
                check(resp.status_code == 201, "POST generate returns 201",
                      f"got {resp.status_code}: {resp.data[:200]}")
                gen_payload = json.loads(resp.data)
                check(gen_payload['created'] == 4,
                      "created equals the number of deduped slots in the fixture catalog",
                      f"got {gen_payload['created']}")
                check(gen_payload['total_points'] == 8,
                      "total_points sums the fixture catalog's slot values",
                      f"got {gen_payload['total_points']}")

                resp = client.post(f"/v2/events/{generated.id}/clog/generate")
                check(resp.status_code == 409, "a second generate call is refused",
                      f"got {resp.status_code}")

            print("\n── Per-event isolation ──────────────────────────────────────")
            # The handler scores every active clog event inside its own try/except so
            # that one event blowing up cannot cost the others their score. Two active
            # events, one player on a team in each, and scoring forced to raise for
            # only one of them. Deliberately order-agnostic: the guarantee holds
            # whichever event the handler reaches first.
            broken_ev = make_event("Test CLOG isolation broken")
            healthy_ev = make_event("Test CLOG isolation healthy")
            events.extend([broken_ev, healthy_ev])
            clog_service.build_slots(broken_ev.id)
            clog_service.build_slots(healthy_ev.id)

            loner = make_user("Clog Loner", "clog_loner")
            users.append(loner)
            broken_team = make_team(broken_ev, "Broken", [loner])
            healthy_team = make_team(healthy_ev, "Healthy", [loner])

            broken_slot = ClogSlot.query.filter_by(event_id=broken_ev.id, item_id=12922).first()
            healthy_slot = ClogSlot.query.filter_by(event_id=healthy_ev.id, item_id=12922).first()
            broken_challenge_id = broken_slot.challenge_id

            original_update = ChallengeEvaluator.update_challenge_status

            def _boom(challenge_id, team_id, quantity_to_add):
                if str(challenge_id) == str(broken_challenge_id):
                    raise RuntimeError("simulated scoring failure")
                return original_update(challenge_id, team_id, quantity_to_add)

            ChallengeEvaluator.update_challenge_status = staticmethod(_boom)
            try:
                submit("Clog Loner", "Tanzanite fang", source="Zulrah")
            finally:
                # Restore before any assertion, so a failure here cannot leak a
                # sabotaged evaluator into the remaining checks or the cleanup.
                ChallengeEvaluator.update_challenge_status = staticmethod(original_update)

            db.session.expire_all()
            healthy_status = ChallengeStatus.query.filter_by(
                team_id=healthy_team.id, challenge_id=healthy_slot.challenge_id,
            ).first()
            broken_status = ChallengeStatus.query.filter_by(
                team_id=broken_team.id, challenge_id=broken_challenge_id,
            ).first()
            check(healthy_status is not None and healthy_status.completed,
                  "one event raising does not cost another event its score",
                  f"healthy status={healthy_status and healthy_status.completed}")
            check(broken_status is None or not broken_status.completed,
                  "and the event whose scoring raised recorded nothing",
                  f"broken status={broken_status and broken_status.completed}")

        finally:
            print("\n── Cleanup ─────────────────────────────────────────────────")
            _cleanup(events, users)

        print("\n" + "=" * 70)
        print(f"  RESULTS: {_pass} passed, {_fail} failed")
        print("=" * 70 + "\n")
        return 1 if _fail else 0


def _cleanup(events, users):
    try:
        for event in events:
            Team.query.filter_by(event_id=event.id).delete(synchronize_session=False)
            for slot in ClogSlot.query.filter_by(event_id=event.id).all():
                challenge_id = slot.challenge_id
                db.session.delete(slot)
                db.session.flush()
                if challenge_id:
                    Challenge.query.filter_by(id=challenge_id).delete(synchronize_session=False)
            db.session.delete(event)
        for user in users:
            db.session.delete(user)
        db.session.query(CollectionLogItem).delete()
        db.session.commit()
    except Exception as exc:
        print(f"  [cleanup warning: {exc}]")
        db.session.rollback()


if __name__ == "__main__":
    sys.exit(run())
