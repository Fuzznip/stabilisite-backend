"""Insert sample collection log drops for local development.

Picks real item ids from the seeded catalog and real members from the users
table, so the website renders exactly as it would with live Dink data. Drops are
spread over the last few days so "recent" ordering and relative timestamps look
realistic.

This writes to whatever DATABASE_URL points at, and the checked-in .env points
at PRODUCTION. Always pass a local database explicitly (DATABASE_URL is a bare
host:port/name — app.py prepends the scheme and credentials):

    DATABASE_URL="localhost:5432/clog_local" DATABASE_USERNAME=postgres \
        DATABASE_PASSWORD= PYTHONPATH=. python scripts/seed_sample_drops.py [count]

Every row it creates is tagged with source=SAMPLE_SOURCE, so they can be removed
again with:  python scripts/seed_sample_drops.py --clear
"""
import datetime
import os
import random
import sys

from app import app, db
from models.models import CollectionLogDrop, CollectionLogItem, Users

DEFAULT_COUNT = 20
# Lets sample rows be identified and deleted later without touching real drops.
SAMPLE_SOURCE = "Sample data"


def _guard_production():
    url = os.environ.get("DATABASE_URL", "")
    if "localhost" in url or "127.0.0.1" in url:
        return
    print(
        "Refusing to run: DATABASE_URL does not look local.\n"
        f"  DATABASE_URL = {url or '(unset)'}\n"
        "Re-run with an explicit local database, e.g.\n"
        '  DATABASE_URL="localhost:5432/clog_local" DATABASE_USERNAME=postgres '
        "DATABASE_PASSWORD= PYTHONPATH=. python scripts/seed_sample_drops.py",
        file=sys.stderr,
    )
    sys.exit(1)


def clear():
    with app.app_context():
        removed = db.session.query(CollectionLogDrop).filter(
            CollectionLogDrop.source == SAMPLE_SOURCE
        ).delete()
        db.session.commit()
        print(f"Removed {removed} sample drops.")


def seed(count):
    with app.app_context():
        catalog = db.session.query(
            CollectionLogItem.item_id, CollectionLogItem.name
        ).distinct().all()
        if not catalog:
            print("Catalog is empty — run scripts/seed_collection_log.py first.", file=sys.stderr)
            sys.exit(1)

        members = db.session.query(Users.discord_id, Users.runescape_name).filter(
            Users.runescape_name.isnot(None)
        ).all()
        if not members:
            print("No users to attribute drops to.", file=sys.stderr)
            sys.exit(1)

        now = datetime.datetime.now(datetime.timezone.utc)
        rows = []
        for i in range(count):
            item_id, item_name = random.choice(catalog)
            discord_id, rsn = random.choice(members)
            rows.append({
                "discord_id": discord_id,
                "rsn": rsn,
                "item_id": item_id,
                "item_name": item_name,
                "source": SAMPLE_SOURCE,
                "quantity": 1,
                "value": 0,
                # Newest first, roughly a few hours apart.
                "timestamp": now - datetime.timedelta(hours=i * 7 + random.randint(0, 5)),
            })

        db.session.bulk_insert_mappings(CollectionLogDrop, rows)
        db.session.commit()
        print(f"Inserted {len(rows)} sample drops (source={SAMPLE_SOURCE!r}).")
        for row in rows[:5]:
            print(f"  {row['rsn']} received {row['item_name']} ({row['item_id']})")


if __name__ == "__main__":
    _guard_production()
    if "--clear" in sys.argv:
        clear()
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("-")]
        seed(int(args[0]) if args else DEFAULT_COUNT)
