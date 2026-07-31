"""Seed the collection_log_items catalog table from data/collection_log_catalog.json.

Idempotent full refresh: clears the catalog and re-inserts every placement. The
drops table (collection_log_drops) references item ids directly and is untouched.

Run:  python scripts/seed_collection_log.py
Regenerate the source data first with scripts/generate_collection_log_catalog.py.
"""
import json
import os

from app import app, db
from models.models import CollectionLogItem

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "collection_log_catalog.json")


def seed():
    with open(DATA_PATH) as f:
        catalog = json.load(f)

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
    seed()
