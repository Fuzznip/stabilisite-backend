#!/usr/bin/env python3
"""
Conquest event test suite.
Run from the project root: PYTHONPATH=. python tests/test_conquest.py

Covers:
  - REST endpoint validation (200/400/404, conquest-type guard)
  - Region / territory / event-log CRUD
  - Full action-processing pipeline (territory control, region control, green log)
  - Scoring correctness after each phase
  - Partial completions (challenge.quantity > 1)
  - Tie-break rule (challenger must strictly exceed current holder)
  - Idempotency (duplicate request_id)
  - Unknown user and teamless user edge cases
  - Green log is awarded only once per team/region
"""

import datetime
import sys
import uuid
from datetime import timedelta, timezone

from app import app, db
from event_handlers.event_handler import EventSubmission
from event_handlers.conquest.conquest import conquest_handler
from models.models import Users
from models.new_events import (
    Action, Challenge, ChallengeStatus, Event,
    EventLog, Region, Team, TeamMember, Territory, Trigger,
)
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_pass = 0
_fail = 0


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
    return conquest_handler(EventSubmission(
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


def fresh(model_class, obj_id):
    """Re-query a model by primary key to bypass session cache."""
    db.session.expire_all()
    return model_class.query.get(obj_id)


def _purge_stale_test_data():
    """
    Remove any leftover test data from a previous crashed run.
    Safe to call even if nothing is stale — all queries use LIKE patterns
    that only match test-created objects.
    """
    try:
        # Stale challenges: find via triggers named GoblinKC_%, CoinsDP_%, BigBones_%
        stale_triggers = Trigger.query.filter(
            Trigger.name.like("GoblinKC_%") |
            Trigger.name.like("CoinsDP_%") |
            Trigger.name.like("BigBones_%")
        ).all()
        for t in stale_triggers:
            stale_challs = Challenge.query.filter_by(trigger_id=t.id).all()
            for c in stale_challs:
                db.session.delete(c)
        db.session.flush()

        for t in stale_triggers:
            db.session.delete(t)
        db.session.flush()

        # Stale events (cascade deletes teams, regions, territories, event_logs)
        stale_events = Event.query.filter(
            Event.name.like("Test Conquest %") |
            Event.name.like("Test Bingo %")
        ).all()
        for e in stale_events:
            db.session.delete(e)
        db.session.flush()

        # Stale users (cascade deletes actions)
        stale_users = Users.query.filter(
            Users.discord_id.like("red_%") |
            Users.discord_id.like("blue_%") |
            Users.discord_id.like("lone_%")
        ).all()
        for u in stale_users:
            db.session.delete(u)

        db.session.commit()
    except Exception as exc:
        print(f"  [pre-cleanup warning: {exc}]")
        db.session.rollback()


def _cleanup(challenges, triggers, events, users):
    """Delete test objects in dependency order. Safe to call with None entries."""
    try:
        db.session.rollback()
        for c in challenges:
            obj = Challenge.query.get(c.id) if c else None
            if obj:
                db.session.delete(obj)
        db.session.flush()
        for t in triggers:
            obj = Trigger.query.get(t.id) if t else None
            if obj:
                db.session.delete(obj)
        db.session.flush()
        for e in events:
            obj = Event.query.get(e.id) if e else None
            if obj:
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
        print("  CONQUEST EVENT TEST SUITE")
        print("=" * 70)

        now = datetime.datetime.now(timezone.utc)
        uid = uuid.uuid4().hex[:8]   # unique suffix so tests don't collide

        print("\n── Pre-cleanup (stale data from previous runs) ──────────────")
        _purge_stale_test_data()

        # Declare all test objects before the try so finally can reference them
        red_user = blue_user = lone_user = None
        conquest = bingo = None
        goblin_t = coins_t = bones_t = None
        challenge_a = challenge_b = challenge_c = None

        try:

            # ================================================================
            # SETUP
            # ================================================================
            print("\n── Setup ───────────────────────────────────────────────────")

            # Users
            red_user  = Users(discord_id=f"red_{uid}",  runescape_name=f"RedPlayer_{uid}")
            blue_user = Users(discord_id=f"blue_{uid}", runescape_name=f"BluePlayer_{uid}")
            lone_user = Users(discord_id=f"lone_{uid}", runescape_name=f"LonePlayer_{uid}")
            db.session.add_all([red_user, blue_user, lone_user])
            db.session.flush()

            # Conquest event (active)
            conquest = Event(
                name=f"Test Conquest {uid}",
                type="conquest",
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(days=7),
            )
            # Bingo event — different type, used to verify non-conquest 400 responses
            bingo = Event(
                name=f"Test Bingo {uid}",
                type="bingo",
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(days=7),
            )
            db.session.add_all([conquest, bingo])
            db.session.flush()

            # Teams
            red_team  = Team(event_id=conquest.id, name=f"Red_{uid}")
            blue_team = Team(event_id=conquest.id, name=f"Blue_{uid}")
            db.session.add_all([red_team, blue_team])
            db.session.flush()

            # lone_user intentionally has NO team membership in the conquest event
            db.session.add_all([
                TeamMember(team_id=red_team.id,  user_id=red_user.id),
                TeamMember(team_id=blue_team.id, user_id=blue_user.id),
            ])

            # Triggers (unique names to avoid collisions with production data)
            goblin_t  = Trigger(name=f"GoblinKC_{uid}",   type="KC")
            coins_t   = Trigger(name=f"CoinsDP_{uid}",    type="DROP")
            bones_t   = Trigger(name=f"BigBones_{uid}",   type="DROP")
            db.session.add_all([goblin_t, coins_t, bones_t])
            db.session.flush()

            # Challenges — task_id=None (conquest challenges are not under tiles/tasks)
            # challenge_a: 1 Goblin KC  → territory A (quantity=1, so 1 kill = 1 completion)
            # challenge_b: 1 Coins DROP → territory B (quantity=1)
            # challenge_c: 3 Big Bones  → territory C (quantity=3, partial-completion test)
            challenge_a = Challenge(task_id=None, trigger_id=goblin_t.id,  quantity=1, value=1)
            challenge_b = Challenge(task_id=None, trigger_id=coins_t.id,   quantity=1, value=1)
            challenge_c = Challenge(task_id=None, trigger_id=bones_t.id,   quantity=3, value=1)
            db.session.add_all([challenge_a, challenge_b, challenge_c])
            db.session.flush()

            # Region + Territories
            region = Region(event_id=conquest.id, name="Misthalin")
            db.session.add(region)
            db.session.flush()

            terr_a = Territory(region_id=region.id, name="Lumbridge", challenge_id=challenge_a.id, display_order=1)
            terr_b = Territory(region_id=region.id, name="Varrock",   challenge_id=challenge_b.id, display_order=2)
            terr_c = Territory(region_id=region.id, name="Draynor",   challenge_id=challenge_c.id, display_order=3)
            db.session.add_all([terr_a, terr_b, terr_c])
            db.session.commit()

            cid  = str(conquest.id)
            bid  = str(bingo.id)
            rsn_red  = red_user.runescape_name
            rsn_blue = blue_user.runescape_name
            rsn_lone = lone_user.runescape_name

            print(f"  conquest event : {cid}")
            print(f"  red_team       : {str(red_team.id)[:8]}…   blue_team: {str(blue_team.id)[:8]}…")
            print(f"  territories    : {terr_a.name}(qty=1)  {terr_b.name}(qty=1)  {terr_c.name}(qty=3)")

            # ================================================================
            # S1 — REST endpoint validation
            # ================================================================
            print("\n── S1: REST endpoint validation ────────────────────────────")

            r = client.get("/v2/events/00000000-0000-0000-0000-000000000000/regions")
            check(r.status_code == 404, "GET /regions: unknown event_id → 404")

            r = client.get(f"/v2/events/{bid}/regions")
            check(r.status_code == 400, "GET /regions: non-conquest event → 400")

            r = client.get(f"/v2/events/{cid}/regions")
            check(r.status_code == 200, "GET /regions: conquest event → 200")
            body = r.get_json()
            check(len(body["data"]) == 1,                               "GET /regions: 1 region returned")
            check(body["data"][0]["name"] == "Misthalin",               "GET /regions: correct name")
            check(body["data"][0]["controlling_team_id"] is None,       "GET /regions: no controller yet")
            check(body["data"][0]["green_logged_teams"] == [],          "GET /regions: empty green_logged_teams")

            r = client.get(f"/v2/events/{bid}/territories")
            check(r.status_code == 400, "GET /territories: non-conquest event → 400")

            r = client.get(f"/v2/events/{cid}/territories")
            check(r.status_code == 200, "GET /territories: conquest event → 200")
            body = r.get_json()
            check(len(body["data"]) == 3,                               "GET /territories: 3 territories returned")
            t_names = {t["name"] for t in body["data"]}
            check(t_names == {"Lumbridge", "Varrock", "Draynor"},       "GET /territories: correct names")
            challenge_ids = {t["challenge_id"] for t in body["data"]}
            check(None not in challenge_ids,                            "GET /territories: all have challenge_id set")

            r = client.get(f"/v2/events/{bid}/event-logs")
            check(r.status_code == 400, "GET /event-logs: non-conquest event → 400")

            r = client.get(f"/v2/events/{cid}/event-logs")
            check(r.status_code == 200, "GET /event-logs: conquest event → 200")
            check(r.get_json()["total"] == 0,                           "GET /event-logs: empty initially")

            r = client.post(f"/v2/events/{cid}/regions", json={"name": "Asgarnia"})
            check(r.status_code == 201, "POST /regions: creates region → 201")
            extra_region_id = r.get_json()["id"]

            r = client.post(f"/v2/events/{bid}/regions", json={"name": "ShouldFail"})
            check(r.status_code == 400, "POST /regions: non-conquest event → 400")

            r = client.post(f"/v2/regions/{extra_region_id}/territories", json={"name": "Falador"})
            check(r.status_code == 201, "POST /territories: creates territory → 201")
            extra_territory_id = r.get_json()["id"]

            r = client.put(f"/v2/territories/{extra_territory_id}",
                           json={"name": "Falador Castle", "display_order": 99})
            check(r.status_code == 200,                                 "PUT /territories: update → 200")
            check(r.get_json()["name"] == "Falador Castle",             "PUT /territories: name updated")
            check(r.get_json()["display_order"] == 99,                  "PUT /territories: display_order updated")

            r = client.put("/v2/territories/00000000-0000-0000-0000-000000000000", json={"name": "nope"})
            check(r.status_code == 404, "PUT /territories: unknown id → 404")

            # ================================================================
            # S2 — Unknown user and teamless user
            # ================================================================
            print("\n── S2: Unknown user / teamless user ────────────────────────")

            before = Action.query.count()
            submit("ThisPlayerDoesNotExist_xyz", goblin_t.name, type="KC")
            check(Action.query.count() == before,                       "Unknown user: no action recorded")

            before = Action.query.count()
            submit(rsn_lone, goblin_t.name, type="KC")
            check(Action.query.count() == before + 1,                   "Teamless user: action IS recorded")
            cs_lone = ChallengeStatus.query.filter_by(
                challenge_id=challenge_a.id, team_id=red_team.id
            ).first()
            check(cs_lone is None,                                      "Teamless user: no challenge_status created")
            terr_a_obj = fresh(Territory, terr_a.id)
            check(terr_a_obj.controlling_team_id is None,               "Teamless user: territory unchanged")

            # ================================================================
            # S3 — First completion: territory + region assigned to Red
            # ================================================================
            print("\n── S3: First completion → territory & region assigned ──────")

            submit(rsn_red, goblin_t.name, type="KC")   # Red: 1 KC → 1 completion (qty=1)
            db.session.expire_all()

            ta = fresh(Territory, terr_a.id)
            rg = fresh(Region, region.id)
            check(ta.controlling_team_id == red_team.id,                "S3: Territory A → Red (1st completion)")
            check(rg.controlling_team_id == red_team.id,                "S3: Region → Red (1 territory vs 0)")

            logs = EventLog.query.filter_by(event_id=conquest.id).order_by(EventLog.created_at).all()
            ltypes = [l.type for l in logs]
            check("CHALLENGE_COMPLETED" in ltypes,                      "S3: CHALLENGE_COMPLETED log written")
            check("TERRITORY_CONTROL"   in ltypes,                      "S3: TERRITORY_CONTROL log written")
            check("REGION_CONTROL"      in ltypes,                      "S3: REGION_CONTROL log written")

            # Verify TERRITORY_CONTROL metadata
            tc_log = next(l for l in logs if l.type == "TERRITORY_CONTROL")
            check(tc_log.meta.get("previousTeamId") is None,            "S3: TERRITORY_CONTROL.meta.previousTeamId is None (no prior holder)")
            check(str(tc_log.team_id) == str(red_team.id),              "S3: TERRITORY_CONTROL.team_id = red_team")

            red = fresh(Team, red_team.id)
            # Points: 1 territory(10) + 1 region(50) + 1 completion(1) = 61
            check(red.points == 61,                                     f"S3: Red points = 61 (got {red.points})")
            blue = fresh(Team, blue_team.id)
            check(blue.points == 0,                                     f"S3: Blue points = 0 (got {blue.points})")

            # ================================================================
            # S4 — Tie rule: challenger matches current holder → no change
            # ================================================================
            print("\n── S4: Tie rule ─────────────────────────────────────────────")

            tc_count_before = EventLog.query.filter_by(event_id=conquest.id, type="TERRITORY_CONTROL").count()
            submit(rsn_blue, goblin_t.name, type="KC")   # Blue: 1 completion = Red's 1 → tie
            db.session.expire_all()

            ta = fresh(Territory, terr_a.id)
            rg = fresh(Region, region.id)
            check(ta.controlling_team_id == red_team.id,                "S4: Tie — Territory A stays Red")
            check(rg.controlling_team_id == red_team.id,                "S4: Tie — Region stays Red")
            tc_count_after = EventLog.query.filter_by(event_id=conquest.id, type="TERRITORY_CONTROL").count()
            check(tc_count_after == tc_count_before,                    "S4: No new TERRITORY_CONTROL log on tie")

            # ================================================================
            # S5 — Overtake: Blue exceeds Red → takes Territory A + Region
            # ================================================================
            print("\n── S5: Overtake ─────────────────────────────────────────────")

            rc_count_before = EventLog.query.filter_by(event_id=conquest.id, type="REGION_CONTROL").count()
            submit(rsn_blue, goblin_t.name, type="KC")   # Blue: 2 completions > Red's 1
            db.session.expire_all()

            ta = fresh(Territory, terr_a.id)
            rg = fresh(Region, region.id)
            check(ta.controlling_team_id == blue_team.id,               "S5: Blue (2) > Red (1) → Territory A → Blue")
            check(rg.controlling_team_id == blue_team.id,               "S5: Blue controls 1 territory, Red 0 → Region → Blue")

            tc_log2 = EventLog.query.filter_by(
                event_id=conquest.id, type="TERRITORY_CONTROL", entity_id=terr_a.id
            ).order_by(EventLog.created_at.desc()).first()
            check(str(tc_log2.meta.get("previousTeamId")) == str(red_team.id),
                  "S5: TERRITORY_CONTROL.meta.previousTeamId = red_team")

            rc_after = EventLog.query.filter_by(event_id=conquest.id, type="REGION_CONTROL").count()
            check(rc_after == rc_count_before + 1,                      "S5: New REGION_CONTROL log written")

            red  = fresh(Team, red_team.id)
            blue = fresh(Team, blue_team.id)
            # Blue: 1 territory(10) + 1 region(50) + 2 completions(2) = 62
            check(blue.points == 62,                                    f"S5: Blue points = 62 (got {blue.points})")
            # Red: 0 territory + 0 region + 1 completion = 1
            check(red.points == 1,                                      f"S5: Red points = 1 (got {red.points})")

            # ================================================================
            # S6 — Red takes Territory B; region tied (1-1) → Blue keeps region
            # ================================================================
            print("\n── S6: Territory B captured; region 1-1 tie ────────────────")

            rc_count_before = EventLog.query.filter_by(event_id=conquest.id, type="REGION_CONTROL").count()
            submit(rsn_red, coins_t.name, type="DROP")   # Red: 1 completion → Territory B
            db.session.expire_all()

            tb = fresh(Territory, terr_b.id)
            rg = fresh(Region, region.id)
            check(tb.controlling_team_id == red_team.id,                "S6: Territory B → Red (1st completion)")
            check(rg.controlling_team_id == blue_team.id,               "S6: Region stays Blue (1-1 tie, Blue is holder)")
            rc_after = EventLog.query.filter_by(event_id=conquest.id, type="REGION_CONTROL").count()
            check(rc_after == rc_count_before,                          "S6: No REGION_CONTROL log on 1-1 tie")

            # Another tie: Blue also gets 1 completion on Territory B → tie, Red keeps
            tc_count_before = EventLog.query.filter_by(event_id=conquest.id, type="TERRITORY_CONTROL").count()
            submit(rsn_blue, coins_t.name, type="DROP")
            db.session.expire_all()

            tb = fresh(Territory, terr_b.id)
            check(tb.controlling_team_id == red_team.id,                "S6: Territory B tie (1-1) — Red keeps control")
            tc_after = EventLog.query.filter_by(event_id=conquest.id, type="TERRITORY_CONTROL").count()
            check(tc_after == tc_count_before,                          "S6: No TERRITORY_CONTROL log on Territory B tie")

            # ================================================================
            # S7 — Red recaptures Territory A (2 more KCs → 3 total > Blue's 2)
            #       Red now controls both → takes region
            #       Red has ≥1 completion on all 3 territories? No — Territory C untouched.
            #       So no green log yet.
            # ================================================================
            print("\n── S7: Red retakes Territory A + Region (no green log yet) ─")

            gl_count_before = EventLog.query.filter_by(event_id=conquest.id, type="GREEN_LOG").count()
            submit(rsn_red, goblin_t.name, type="KC")   # Red: 2 completions — still tied
            submit(rsn_red, goblin_t.name, type="KC")   # Red: 3 completions > Blue's 2 → takes back
            db.session.expire_all()

            ta = fresh(Territory, terr_a.id)
            rg = fresh(Region, region.id)
            check(ta.controlling_team_id == red_team.id,                "S7: Red (3 KC) > Blue (2 KC) → Territory A → Red")
            check(rg.controlling_team_id == red_team.id,                "S7: Red controls A+B → Region → Red")

            gl_after = EventLog.query.filter_by(event_id=conquest.id, type="GREEN_LOG").count()
            check(gl_after == gl_count_before,                          "S7: No green log (Territory C still untouched)")

            region_ctrl_log = EventLog.query.filter_by(
                event_id=conquest.id, type="REGION_CONTROL"
            ).order_by(EventLog.created_at.desc()).first()
            check(str(region_ctrl_log.meta.get("previousTeamId")) == str(blue_team.id),
                  "S7: REGION_CONTROL.meta.previousTeamId = blue_team")

            # ================================================================
            # S8 — Partial completion (Territory C, challenge.quantity = 3)
            # ================================================================
            print("\n── S8: Partial completion (qty=3 challenge) ────────────────")

            submit(rsn_red, bones_t.name, type="DROP")   # qty=1, need 3 → no completion
            db.session.expire_all()
            tc = fresh(Territory, terr_c.id)
            check(tc.controlling_team_id is None,                       "S8: No control at quantity 1/3")

            submit(rsn_red, bones_t.name, type="DROP")   # qty=2 → still no completion
            db.session.expire_all()
            tc = fresh(Territory, terr_c.id)
            check(tc.controlling_team_id is None,                       "S8: No control at quantity 2/3")

            gl_before_c = EventLog.query.filter_by(event_id=conquest.id, type="GREEN_LOG").count()
            submit(rsn_red, bones_t.name, type="DROP")   # qty=3 → 1st completion → Territory C
            db.session.expire_all()

            tc = fresh(Territory, terr_c.id)
            check(tc.controlling_team_id == red_team.id,                "S8: Territory C → Red at qty 3/3 (1st completion)")

            # Now Red controls A, B, C and has ≥1 completion on all → Green Log
            rg = fresh(Region, region.id)
            gl_after_c = EventLog.query.filter_by(event_id=conquest.id, type="GREEN_LOG").count()
            check(gl_after_c == gl_before_c + 1,                        "S8: GREEN_LOG written after completing all territories")

            gl_log = EventLog.query.filter_by(event_id=conquest.id, type="GREEN_LOG").first()
            check(str(gl_log.team_id) == str(red_team.id),              "S8: GREEN_LOG.team_id = red_team")
            check(str(gl_log.entity_id) == str(region.id),              "S8: GREEN_LOG.entity_id = region")

            green_logged = [str(t) for t in (rg.green_logged_teams or [])]
            check(str(red_team.id) in green_logged,                     "S8: red_team in region.green_logged_teams")

            # ================================================================
            # S9 — Green log not awarded twice
            # ================================================================
            print("\n── S9: Green log idempotency ────────────────────────────────")

            gl_count = EventLog.query.filter_by(event_id=conquest.id, type="GREEN_LOG").count()
            submit(rsn_red, goblin_t.name, type="KC")   # another completion — all territories still done
            db.session.expire_all()
            check(EventLog.query.filter_by(event_id=conquest.id, type="GREEN_LOG").count() == gl_count,
                  "S9: Green log NOT re-awarded on subsequent completions")

            rg = fresh(Region, region.id)
            green_logged = [str(t) for t in (rg.green_logged_teams or [])]
            check(green_logged.count(str(red_team.id)) == 1,            "S9: red_team appears exactly once in green_logged_teams")

            # ================================================================
            # S10 — Scoring verification
            # ================================================================
            print("\n── S10: Scoring verification ────────────────────────────────")

            db.session.expire_all()
            red  = fresh(Team, red_team.id)
            blue = fresh(Team, blue_team.id)

            # Red completions at this point:
            #   Territory A (goblin KC, qty=1): S3(1) + S7(1+1) + S9(1) = 4 completions
            #   Territory B (coins DROP, qty=1): S6(1) = 1 completion
            #   Territory C (big bones, qty=3): S8(1+1+1)=qty3 = 1 completion
            # Red controls: Territory A, B, C (3) → 30  |  Region (1) → 50
            # Task completions: 4 + 1 + 1 = 6 → 6
            # Green logs: 1 → 15
            # Red total = 30 + 50 + 6 + 15 = 101

            # Blue completions:
            #   Territory A (goblin KC): S4(1) + S5(1) = 2 completions
            #   Territory B (coins DROP): S6(1) = 1 completion
            # Blue controls: nothing → 0
            # Task completions: 2 + 1 = 3 → 3
            # Blue total = 3

            expected_red  = 101
            expected_blue = 3
            check(red.points  == expected_red,  f"S10: Red points  = {expected_red}  (got {red.points})")
            check(blue.points == expected_blue, f"S10: Blue points = {expected_blue} (got {blue.points})")

            # ================================================================
            # S11 — Duplicate request_id (idempotency)
            # ================================================================
            print("\n── S11: Duplicate request_id (idempotency) ─────────────────")

            req_id = f"test-req-{uid}"
            submit(rsn_red, goblin_t.name, type="KC", request_id=req_id)
            red_points_after_first = fresh(Team, red_team.id).points

            submit(rsn_red, goblin_t.name, type="KC", request_id=req_id)   # duplicate
            db.session.expire_all()

            actions_with_req = Action.query.filter_by(request_id=req_id).count()
            check(actions_with_req == 1,                                "S11: Only 1 action stored for duplicate request_id")
            check(fresh(Team, red_team.id).points == red_points_after_first,
                  "S11: Points unchanged after duplicate submission")

            # ================================================================
            # S12 — Non-matching trigger
            # ================================================================
            print("\n── S12: Non-matching trigger ────────────────────────────────")

            ta_ctrl_before = fresh(Territory, terr_a.id).controlling_team_id
            log_count_before = EventLog.query.filter_by(event_id=conquest.id).count()
            submit(rsn_red, f"ZulrahDropNotReal_{uid}", type="DROP")
            db.session.expire_all()

            check(fresh(Territory, terr_a.id).controlling_team_id == ta_ctrl_before,
                  "S12: Territory unchanged for non-matching trigger")
            check(EventLog.query.filter_by(event_id=conquest.id).count() == log_count_before,
                  "S12: No event logs written for non-matching trigger")

            # ================================================================
            # S13 — Event log endpoint: pagination + content
            # ================================================================
            print("\n── S13: Event log endpoint ──────────────────────────────────")

            r = client.get(f"/v2/events/{cid}/event-logs")
            body = r.get_json()
            check(body["total"] > 0,                                    "S13: event-logs has entries")
            log_types = {l["type"] for l in body["data"]}
            check("CHALLENGE_COMPLETED" in log_types,                   "S13: CHALLENGE_COMPLETED present")
            check("TERRITORY_CONTROL"   in log_types,                   "S13: TERRITORY_CONTROL present")
            check("REGION_CONTROL"      in log_types,                   "S13: REGION_CONTROL present")
            check("GREEN_LOG"           in log_types,                   "S13: GREEN_LOG present")

            r2 = client.get(f"/v2/events/{cid}/event-logs?per_page=3&page=1")
            body2 = r2.get_json()
            check(body2["per_page"] == 3,                               "S13: per_page param respected")
            check(len(body2["data"]) <= 3,                              "S13: at most per_page entries returned")
            check(body2["total"] == body["total"],                      "S13: total count consistent across pages")

            # Logs are newest first
            if len(body["data"]) >= 2:
                ts0 = body["data"][0]["created_at"]
                ts1 = body["data"][1]["created_at"]
                check(ts0 >= ts1,                                       "S13: event-logs ordered newest first")

            # Each log has required fields
            sample = body["data"][0]
            for field in ("id", "event_id", "team_id", "type", "created_at"):
                check(field in sample,                                  f"S13: log entry has field '{field}'")

            # ================================================================
            # S14 — Territories endpoint reflects live state
            # ================================================================
            print("\n── S14: Territory endpoint reflects live state ──────────────")

            r = client.get(f"/v2/events/{cid}/territories")
            body = r.get_json()
            by_name = {t["name"]: t for t in body["data"]}

            check(str(by_name["Lumbridge"]["controlling_team_id"]) == str(red_team.id),
                  "S14: Territory A (Lumbridge) shows Red as controller")
            check(str(by_name["Varrock"]["controlling_team_id"]) == str(red_team.id),
                  "S14: Territory B (Varrock) shows Red as controller")
            check(str(by_name["Draynor"]["controlling_team_id"]) == str(red_team.id),
                  "S14: Territory C (Draynor) shows Red as controller")

            r = client.get(f"/v2/events/{cid}/regions")
            regions_data = {rg["name"]: rg for rg in r.get_json()["data"]}
            region_data = regions_data["Misthalin"]
            check(str(region_data["controlling_team_id"]) == str(red_team.id),
                  "S14: Region shows Red as controller")
            check(str(red_team.id) in region_data["green_logged_teams"],
                  "S14: Region green_logged_teams contains red_team")

        finally:
            print("\n── Cleanup ──────────────────────────────────────────────────")
            _cleanup(
                challenges=[challenge_a, challenge_b, challenge_c],
                triggers=[goblin_t, coins_t, bones_t],
                events=[conquest, bingo],
                users=[red_user, blue_user, lone_user],
            )

        # ================================================================
        # SUMMARY
        # ================================================================
        print("\n" + "=" * 70)
        total = _pass + _fail
        print(f"  {_pass}/{total} passed   {'✅ all clear' if _fail == 0 else f'❌ {_fail} failed'}")
        print("=" * 70 + "\n")

        return _fail


if __name__ == "__main__":
    sys.exit(run())
