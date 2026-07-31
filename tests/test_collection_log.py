import pytest
from app import app, db
from models.models import Users, CollectionLogItem, CollectionLogDrop
from datetime import datetime, timezone


@pytest.fixture
def test_client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


@pytest.fixture
def test_user():
    user = Users(
        discord_id="12345",
        runescape_name="TestUser",
        is_active=True,
        is_member=True,
        join_date=datetime.now(timezone.utc),
        timestamp=datetime.now(timezone.utc),
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def catalog():
    rows = [
        CollectionLogItem(item_id=12922, name="Tanzanite fang", category="Bosses", page="Zulrah", page_order=1, sequence=0),
        CollectionLogItem(item_id=12921, name="Pet snakeling", category="Bosses", page="Zulrah", page_order=1, sequence=1),
        CollectionLogItem(item_id=20851, name="Twisted bow", category="Raids", page="Chambers of Xeric", page_order=2, sequence=0),
        # multi-page: a pet also appears under All Pets (Other comes after Raids in-game)
        CollectionLogItem(item_id=12921, name="Pet snakeling", category="Other", page="All Pets", page_order=3, sequence=0),
    ]
    db.session.add_all(rows)
    db.session.commit()
    return rows


def _submit(client, **overrides):
    payload = {
        "rsn": "TestUser",
        "id": None,
        "trigger": "Tanzanite fang",
        "source": "Zulrah",
        "quantity": 1,
        "totalValue": 5000000,
        "type": "CLOG",
        "item_id": 12922,
    }
    payload.update(overrides)
    return client.post("/events/submit", json=payload)


def test_clog_submission_records_drop_and_resolves_member(test_client, test_user):
    resp = _submit(test_client)
    assert resp.status_code == 200
    assert CollectionLogDrop.query.count() == 1
    drop = CollectionLogDrop.query.first()
    assert drop.item_id == 12922
    assert drop.rsn == "TestUser"
    assert drop.discord_id == "12345"  # resolved by RSN


def test_member_resolution_by_alt_name(test_client, test_user):
    test_user.alt_names = ["AltAcct"]
    db.session.commit()
    resp = _submit(test_client, rsn="AltAcct", trigger="Pet snakeling", item_id=12921)
    assert resp.status_code == 200
    assert CollectionLogDrop.query.first().discord_id == "12345"


def test_unmatched_rsn_stored_without_member(test_client, test_user):
    resp = _submit(test_client, rsn="SomeRandom")
    assert resp.status_code == 200
    drop = CollectionLogDrop.query.first()
    assert drop.discord_id is None
    assert drop.rsn == "SomeRandom"


def test_non_clog_type_ignored(test_client, test_user):
    resp = _submit(test_client, type="LOOT")
    assert resp.status_code == 200
    assert CollectionLogDrop.query.count() == 0


def test_missing_item_id_ignored(test_client, test_user):
    resp = _submit(test_client, item_id=None)
    assert resp.status_code == 200
    assert CollectionLogDrop.query.count() == 0


def test_duplicates_are_kept(test_client, test_user):
    _submit(test_client)
    _submit(test_client)
    assert CollectionLogDrop.query.count() == 2


def test_summary_endpoint_aggregates(test_client, test_user):
    _submit(test_client)
    _submit(test_client)  # same member, same item -> 1 member, 2 total
    resp = test_client.get("/collection-log/summary")
    assert resp.status_code == 200
    data = resp.get_json()
    row = next(r for r in data if r["item_id"] == 12922)
    assert row["member_count"] == 1
    assert row["total_count"] == 2


def test_item_members_endpoint(test_client, test_user):
    _submit(test_client)
    resp = test_client.get("/collection-log/item/12922")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["runescape_name"] == "TestUser"
    assert data[0]["count"] == 1
    assert data[0]["first_obtained"] is not None


def test_catalog_endpoint_structure(test_client, catalog):
    resp = test_client.get("/collection-log/catalog")
    assert resp.status_code == 200
    data = resp.get_json()
    categories = [c["category"] for c in data]
    assert categories == ["Bosses", "Raids", "Other"]  # ordered by page_order
    bosses = next(c for c in data if c["category"] == "Bosses")
    zulrah = next(p for p in bosses["pages"] if p["page"] == "Zulrah")
    assert [i["name"] for i in zulrah["items"]] == ["Tanzanite fang", "Pet snakeling"]


def test_items_endpoint_returns_distinct_ids(test_client, catalog):
    resp = test_client.get("/collection-log/items")
    assert resp.status_code == 200
    ids = resp.get_json()
    # 12921 appears on two pages but should be distinct here
    assert sorted(ids) == [12921, 12922, 20851]
