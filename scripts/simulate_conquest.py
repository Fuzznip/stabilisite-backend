"""
Simulate conquest event activity by submitting random actions against the remote API.

Usage:
    python scripts/simulate_conquest.py [--count 100] [--delay 1.0] [--event-id <uuid>]

Defaults to 100 actions, 1s between each, targeting the active conquest event.
"""

import argparse
import random
import time

import psycopg2
import requests

REMOTE_DB_URL = "postgresql://postgres:LKQvXMhlGSXmKAXbJrpLbzzVkSnuhdOi@metro.proxy.rlwy.net:18969/railway"
REMOTE_API_URL = "https://stability-backend-prototypes-production.up.railway.app/events/submit"

EVENT_ID = "8986ee4e-e5e2-4d55-ad99-b9f26436a14e"


def load_simulation_data(event_id: str):
    conn = psycopg2.connect(REMOTE_DB_URL)
    cur = conn.cursor()

    cur.execute("""
        SELECT tr.name, tr.source
        FROM new_stability.territories terr
        JOIN new_stability.challenges c ON c.id = terr.challenge_id
        JOIN new_stability.triggers tr ON tr.id = c.trigger_id
        WHERE terr.challenge_id IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM new_stability.regions r WHERE r.id = terr.region_id AND r.event_id = %s
          )
    """, (event_id,))
    triggers = cur.fetchall()

    cur.execute("""
        SELECT u.runescape_name
        FROM new_stability.team_members tm
        JOIN users u ON u.id = tm.user_id
        JOIN new_stability.teams t ON t.id = tm.team_id
        WHERE t.event_id = %s AND u.runescape_name IS NOT NULL AND u.runescape_name != ''
    """, (event_id,))
    members = [r[0] for r in cur.fetchall()]

    conn.close()
    return triggers, members


def run(count: int, delay: float, event_id: str):
    print(f"Loading event data for {event_id}...")
    triggers, members = load_simulation_data(event_id)

    if not triggers:
        print("ERROR: No triggers found for this event. Check that territories have challenges assigned.")
        return
    if not members:
        print("ERROR: No team members found for this event.")
        return

    print(f"Loaded {len(triggers)} triggers, {len(members)} members. Submitting {count} actions...\n")

    matched = 0
    unmatched = 0
    errors = 0

    for i in range(count):
        rsn = random.choice(members)
        trigger_name, source = random.choice(triggers)

        payload = {
            "rsn": rsn,
            "trigger": trigger_name,
            "source": source or "",
            "quantity": 1,
            "type": "DROP",
        }

        try:
            resp = requests.post(REMOTE_API_URL, json=payload, timeout=10)
            data = resp.json()
            notifs = data.get("notifications", [])

            if notifs:
                matched += 1
                desc = notifs[0].get("description", "")
                print(f"[{i+1:3d}] {rsn} — {trigger_name}: {desc[:90]}")
            else:
                unmatched += 1
                if (i + 1) % 10 == 0:
                    print(f"[{i+1:3d}] ... {matched} matched, {unmatched} unmatched so far")
        except Exception as e:
            errors += 1
            print(f"[{i+1:3d}] ERROR: {e}")

        if i < count - 1:
            time.sleep(delay)

    print(f"\nDone: {matched} matched, {unmatched} unmatched, {errors} errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate conquest event activity")
    parser.add_argument("--count", type=int, default=100, help="Number of actions to submit (default: 100)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between submissions (default: 1.0)")
    parser.add_argument("--event-id", default=EVENT_ID, help="Conquest event UUID")
    args = parser.parse_args()

    run(args.count, args.delay, args.event_id)
