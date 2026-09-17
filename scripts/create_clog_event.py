"""Create a collection log race event: teams, a random roster, and its slots.

Dry run by default — nothing is written until you pass --commit.

    PYTHONPATH=. .venv/bin/python scripts/create_clog_event.py \
        --name "Collection Log Race" \
        --start 2026-09-24T19:00:00Z --end 2026-09-29T19:00:00Z

The roster is drawn from active members. The shuffle seed is printed so a draw
can be reproduced and audited; pass --seed to repeat one exactly.

thread_id is optional and may be set later with PUT /v2/events/<id>. An event
without one scores normally and posts nothing.
"""
import argparse
import random
import sys
from datetime import datetime

from app import app, db
from models.models import Users
from models.new_events import ClogSlot, Event, Team, TeamMember
from services.clog_service import build_slots, event_slots

TEAM_COUNT = 3
TEAM_SIZE = 20
TEAM_COLORS = ['#C0392B', '#2980B9', '#27AE60']


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--start', required=True, help='ISO 8601, e.g. 2026-09-24T19:00:00Z')
    parser.add_argument('--end', required=True)
    parser.add_argument('--thread-id', default=None)
    parser.add_argument('--release-date', default=None)
    parser.add_argument('--teams', type=int, default=TEAM_COUNT)
    parser.add_argument('--team-size', type=int, default=TEAM_SIZE)
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--commit', action='store_true', help='actually write')
    return parser.parse_args(argv)


def _dt(value: str) -> datetime:
    """Parse an ISO 8601 timestamp, requiring an explicit timezone.

    The columns are timestamptz. A naive value would be interpreted against the
    database session's timezone rather than the operator's intent, silently
    shifting a live event's start and end.
    """
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError(
            f"{value!r} has no timezone. Use an explicit offset, e.g. "
            f"'{value}Z' for UTC (3pm US Eastern in September is 19:00Z)."
        )
    return parsed


def main(argv):
    args = parse_args(argv)

    if args.teams < 1 or args.team_size < 1:
        print(f"ERROR: --teams and --team-size must be >= 1 (got teams={args.teams}, team-size={args.team_size}).")
        return 1

    if args.teams > len(TEAM_COLORS):
        print(f"ABORT: only {len(TEAM_COLORS)} team colours are defined; "
              f"add more to TEAM_COLORS before running {args.teams} teams.")
        return 1

    try:
        start_dt = _dt(args.start)
        end_dt = _dt(args.end)
        release_dt = _dt(args.release_date) if args.release_date else None
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    needed = args.teams * args.team_size

    with app.app_context():
        pool = Users.query.filter_by(is_member=True, is_active=True).all()
        if len(pool) < needed:
            print(f"ABORT: need {needed} active members, found {len(pool)}.")
            return 1

        seed = args.seed if args.seed is not None else random.randrange(2**31)
        rng = random.Random(seed)
        drawn = pool[:]
        rng.shuffle(drawn)
        drawn = drawn[:needed]

        rosters = [
            drawn[i * args.team_size:(i + 1) * args.team_size]
            for i in range(args.teams)
        ]

        print(f"Event:  {args.name}  {args.start} → {args.end}")
        print(f"Thread: {args.thread_id or '(none — notifications suppressed)'}")
        print(f"Pool:   {len(pool)} active members, drawing {needed}")
        print(f"Seed:   {seed}   (pass --seed {seed} to reproduce this draw)")
        for i, roster in enumerate(rosters, start=1):
            print(f"\n  Team {i} ({TEAM_COLORS[i - 1]}):")
            for user in sorted(roster, key=lambda u: u.runescape_name.lower()):
                print(f"    - {user.runescape_name}")

        if not args.commit:
            print("\nDry run. Re-run with --commit to write.")
            return 0

        event = Event(
            name=args.name,
            type='clog',
            thread_id=args.thread_id,
            start_date=start_dt,
            end_date=end_dt,
            release_date=release_dt,
        )
        db.session.add(event)
        db.session.flush()

        for i, roster in enumerate(rosters, start=1):
            team = Team(
                event_id=event.id,
                name=f"Team {i}",
                color=TEAM_COLORS[i - 1],
                points=0,
            )
            db.session.add(team)
            db.session.flush()
            for user in roster:
                db.session.add(TeamMember(team_id=team.id, user_id=user.id))
        db.session.commit()

        print(f"\nCreated event {event.id}")

        try:
            build_slots(event.id)
        except Exception as exc:
            print(f"\nSLOT GENERATION FAILED: {exc}")
            print(f"The event, its teams and its roster ARE already committed as {event.id}.")
            print("Do NOT re-run this script — it would draw a new random roster into a second event.")
            print("Finish this event's slots instead:")
            print(f"  curl -s -X POST $API/v2/events/{event.id}/clog/generate")
            print("Or, to abandon it entirely:")
            print(f"  curl -s -X DELETE $API/v2/events/{event.id}")
            return 1

        rows = event_slots(event.id)

        print(f"  {args.teams} teams × {args.team_size} players")
        print(f"  {len(rows)} slots, {sum(int(c.value or 0) for _, c in rows)} points")
        print("\nNEXT: reload the Dink whitelist, inside the 24h window before start:")
        print("  curl -s -X POST https://stabilidink.up.railway.app/items \\")
        print("    -H 'Content-Type: application/json' -d '{}'")
        print("\nWithout that reload, Dink never sends these items and nothing scores.")
        return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
