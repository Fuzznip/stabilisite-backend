"""Seed the collection_log_items catalog table from the catalog published to S3.

Idempotent full refresh: clears the catalog and re-inserts every placement.
Existing clog_slots rows are unaffected: a collection log race event copies the
catalog fields it needs at creation time rather than joining to this table, so a
re-seed mid-event cannot move a running event's slots.

Once seeded, the table is the only source of collection log structure, and it is
read directly through SQLAlchemy by services/clog_service.py when a collection
log race event is created. GET /collection-log/catalog also serves these rows,
though nothing consumes it now that the site reads /v2/events/<id>/clog/slots —
it is kept as a read-only way to inspect the catalog after a re-seed.

Run:  PYTHONPATH=. .venv/bin/python scripts/seed_collection_log.py

The catalog is not committed. It is generated from the game cache by the website
repo's ./scripts/cache/extract.sh and published with ./scripts/cache/publish.sh.
Reading it needs no AWS credentials — the object is public. Pass --file <path>
to seed from a local copy instead.

It must come from the cache, which reads the collection log enums the client
itself uses. An earlier version scraped the OSRS Wiki, which disagrees on 18 item
ids for the same items (Tea flask 25617 vs 10859, Unsired 25624 vs 13273, the
satchels, the Prospector set) and omits Venator fang/tooth entirely. Because
these rows also drive /collection-log/catalog and the collection log race
generator, ids that don't match what the game reports would surface the wrong
items to players.
"""
import json
import sys

import requests

from app import app, db
from models.models import CollectionLogItem

# Must match CATALOG_KEY in the website repo's scripts/cache/publish.sh.
CATALOG_URL = "https://stability-event.s3.us-east-1.amazonaws.com/collection-log/catalog.json"


def load_catalog(path=None):
    """The published catalog, or a local file when --file is given."""
    if path:
        with open(path) as f:
            return json.load(f), path
    # cache-bust: the object has a short TTL, but a proxy in between shouldn't
    # be able to hand back a stale catalog and seed stale item ids.
    response = requests.get(CATALOG_URL, headers={"Cache-Control": "no-cache"}, timeout=30)
    response.raise_for_status()
    return response.json(), CATALOG_URL


def seed(path=None):
    catalog, source = load_catalog(path)
    print(f"Loaded {len(catalog)} placements from {source}")

    with app.app_context():
        # Only ensure our own table exists (avoid create_all, which also targets
        # the new_stability-schema models and needs that schema pre-created).
        CollectionLogItem.__table__.create(db.engine, checkfirst=True)
        deleted = db.session.query(CollectionLogItem).delete()
        db.session.bulk_insert_mappings(CollectionLogItem, [
            {
                "item_id": row["item_id"],
                "name": row["name"],
                "category": row["category"],
                "page": row["page"],
                "page_order": row["page_order"],
                "sequence": row["sequence"],
                "image_url": row.get("image_url"),
            }
            for row in catalog
        ])
        db.session.commit()
        print(f"Seeded collection_log_items: removed {deleted}, inserted {len(catalog)} placements.")


if __name__ == "__main__":
    local = None
    if "--file" in sys.argv:
        local = sys.argv[sys.argv.index("--file") + 1]
    seed(local)
