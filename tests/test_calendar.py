"""
Calendar entries: model, /v2/calendar endpoints, Discord sync, bot helpers.

conftest.py drops the new_stability schema in whatever database DATABASE_URL
points at, so this file refuses to run unless that is a *_test database:

    DATABASE_URL=localhost:5432/stability_test .venv/bin/python -m pytest tests/test_calendar.py -v
"""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

if not os.getenv("DATABASE_URL", "").endswith("_test"):
    pytest.exit("Point DATABASE_URL at a *_test database; conftest drops new_stability.", returncode=1)

from app import app, db
from models.calendar_entries import CalendarEntry
from models.new_events import Event

NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def tables():
    with app.app_context():
        db.create_all()
    yield
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    yield
    with app.app_context():
        CalendarEntry.query.delete()
        Event.query.delete()
        db.session.commit()


@pytest.fixture
def client():
    return app.test_client()


def make_entry(**overrides):
    fields = dict(
        name="Clan mass", type="adhoc",
        start_date=NOW + timedelta(days=2), end_date=NOW + timedelta(days=3),
        all_day=True, is_public=True, sync_discord=False,
    )
    fields.update(overrides)
    with app.app_context():
        entry = CalendarEntry(**fields)
        db.session.add(entry)
        db.session.commit()
        return str(entry.id)


def test_model_defaults_and_serialize():
    entry_id = make_entry()
    with app.app_context():
        data = CalendarEntry.query.get(entry_id).serialize()
    assert data["id"] == entry_id
    assert data["type"] == "adhoc"
    assert data["discord_event_id"] is None
    assert data["event_id"] is None
    assert datetime.fromisoformat(data["start_date"]).tzinfo is not None


from helper import discord_helper
import requests


def _response(mocker, status=200, body=None):
    resp = mocker.Mock(status_code=status)
    resp.json.return_value = body or {}
    if status >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)
    return resp


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("DISCORD_BOT_API", "https://bot.invalid")
    monkeypatch.setenv("DISCORD_BOT_API_TOKEN", "secret")


def test_helpers_do_nothing_outside_production(mocker):
    post = mocker.patch("helper.discord_helper.requests.post")
    assert discord_helper.discord_sync_enabled() is False
    assert discord_helper.create_discord_scheduled_event("x", NOW, NOW + timedelta(hours=1)) is None
    post.assert_not_called()


def test_create_helper_posts_and_returns_id(mocker, production):
    post = mocker.patch("helper.discord_helper.requests.post", return_value=_response(mocker, body={"id": "42"}))
    start, end = NOW + timedelta(days=1), NOW + timedelta(days=2)
    assert discord_helper.create_discord_scheduled_event("Bingo", start, end) == "42"
    url = post.call_args.args[0]
    body = post.call_args.kwargs["json"]
    assert url == "https://bot.invalid/scheduled-events"
    assert body == {"name": "Bingo", "start_time": start.isoformat(), "end_time": end.isoformat(), "token": "secret"}


def test_create_helper_returns_none_on_error(mocker, production):
    mocker.patch("helper.discord_helper.requests.post", return_value=_response(mocker, status=500))
    assert discord_helper.create_discord_scheduled_event("Bingo", NOW, NOW + timedelta(hours=1)) is None


def test_update_helper_distinguishes_missing(mocker, production):
    patch = mocker.patch("helper.discord_helper.requests.patch")
    patch.return_value = _response(mocker)
    assert discord_helper.update_discord_scheduled_event("42", "B", NOW, NOW + timedelta(hours=1)) == "ok"
    assert patch.call_args.args[0] == "https://bot.invalid/scheduled-events/42"
    patch.return_value = _response(mocker, status=404)
    assert discord_helper.update_discord_scheduled_event("42", "B", NOW, NOW + timedelta(hours=1)) == "missing"
    patch.return_value = _response(mocker, status=500)
    assert discord_helper.update_discord_scheduled_event("42", "B", NOW, NOW + timedelta(hours=1)) == "failed"


def test_delete_helper(mocker, production):
    delete = mocker.patch("helper.discord_helper.requests.delete", return_value=_response(mocker))
    assert discord_helper.delete_discord_scheduled_event("42") is True
    assert delete.call_args.kwargs["json"] == {"token": "secret"}
    delete.return_value = _response(mocker, status=500)
    assert discord_helper.delete_discord_scheduled_event("42") is False


def iso(dt):
    return dt.isoformat()


def payload(**overrides):
    body = {
        "name": "Clan mass", "type": "adhoc",
        "start_date": iso(NOW + timedelta(days=2)), "end_date": iso(NOW + timedelta(days=3)),
        "all_day": True, "is_public": True, "sync_discord": False,
    }
    body.update(overrides)
    return body


def make_event(**overrides):
    fields = dict(name="Fall Bingo", type="bingo",
                  start_date=NOW + timedelta(days=10), end_date=NOW + timedelta(days=17))
    fields.update(overrides)
    with app.app_context():
        event = Event(**fields)
        db.session.add(event)
        db.session.commit()
        return str(event.id)


def test_create_entry(client):
    response = client.post("/v2/calendar", json=payload(name="  Clan mass  "))
    assert response.status_code == 201
    body = response.get_json()
    assert body["discord_sync"] == "skipped"
    assert body["data"]["name"] == "Clan mass"
    assert body["data"]["is_public"] is True


def test_create_entry_linked_to_event(client):
    event_id = make_event()
    response = client.post("/v2/calendar", json=payload(type="bingo", event_id=event_id))
    assert response.status_code == 201
    assert response.get_json()["data"]["event_id"] == event_id


@pytest.mark.parametrize("overrides, message", [
    ({"name": "   "}, "Name is required"),
    ({"name": "x" * 101}, "100 characters or fewer"),  # Discord's scheduled-event limit
    ({"type": "raid"}, "Type must be one of"),
    ({"start_date": "not a date"}, "ISO datetimes"),
    ({"start_date": "2026-11-01T00:00:00"}, "ISO datetimes"),  # no timezone
    ({"end_date": iso(NOW + timedelta(days=1))}, "end_date must be after start_date"),
    ({"event_id": "not-a-uuid"}, "Linked event not found"),
    ({"event_id": "00000000-0000-0000-0000-000000000000"}, "Linked event not found"),
])
def test_create_rejects_invalid(client, overrides, message):
    response = client.post("/v2/calendar", json=payload(**overrides))
    assert response.status_code == 400
    assert message in response.get_json()["error"]


def test_create_rejects_missing_body(client):
    response = client.post("/v2/calendar", data="nope", content_type="text/plain")
    assert response.status_code == 400


def test_get_filters_by_range_and_visibility(client):
    inside = make_entry(name="Inside")
    make_entry(name="Private", is_public=False)
    make_entry(name="Too late", start_date=NOW + timedelta(days=60), end_date=NOW + timedelta(days=61))
    spanning = make_entry(name="Spans in", start_date=NOW - timedelta(days=5), end_date=NOW + timedelta(days=1))
    params = {"from": iso(NOW), "to": iso(NOW + timedelta(days=30))}

    public = client.get("/v2/calendar", query_string=params).get_json()["data"]
    assert [e["id"] for e in public] == [spanning, inside]  # ordered by start_date

    everything = client.get("/v2/calendar", query_string={**params, "include_private": "true"}).get_json()["data"]
    assert {e["name"] for e in everything} == {"Inside", "Private", "Spans in"}


def test_get_requires_valid_range(client):
    assert client.get("/v2/calendar").status_code == 400
    bad = {"from": iso(NOW), "to": iso(NOW - timedelta(days=1))}
    assert client.get("/v2/calendar", query_string=bad).status_code == 400


def test_update_entry(client):
    entry_id = make_entry()
    response = client.put(f"/v2/calendar/{entry_id}", json=payload(name="Renamed", is_public=False))
    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "Renamed"
    assert response.get_json()["data"]["is_public"] is False


def test_update_validates_and_404s(client):
    entry_id = make_entry()
    assert client.put(f"/v2/calendar/{entry_id}", json=payload(type="nope")).status_code == 400
    assert client.put("/v2/calendar/00000000-0000-0000-0000-000000000000", json=payload()).status_code == 404
    assert client.put("/v2/calendar/garbage", json=payload()).status_code == 404


def test_delete_entry(client):
    entry_id = make_entry()
    response = client.delete(f"/v2/calendar/{entry_id}")
    assert response.status_code == 200
    assert response.get_json()["discord_sync"] == "skipped"
    with app.app_context():
        assert CalendarEntry.query.get(entry_id) is None
    assert client.delete(f"/v2/calendar/{entry_id}").status_code == 404


def test_deleting_linked_event_unlinks_entry():
    event_id = make_event()
    entry_id = make_entry(type="bingo", event_id=event_id)
    with app.app_context():
        db.session.delete(Event.query.get(event_id))
        db.session.commit()
        assert CalendarEntry.query.get(entry_id).event_id is None


@pytest.fixture
def bot(mocker):
    mocker.patch("helper.discord_helper.discord_sync_enabled", return_value=True)
    return SimpleNamespace(
        create=mocker.patch("helper.discord_helper.create_discord_scheduled_event", return_value="111"),
        update=mocker.patch("helper.discord_helper.update_discord_scheduled_event", return_value="ok"),
        delete=mocker.patch("helper.discord_helper.delete_discord_scheduled_event", return_value=True),
    )


def stored_discord_id(entry_id):
    with app.app_context():
        return CalendarEntry.query.get(entry_id).discord_event_id


def test_sync_skipped_outside_production(client, mocker):
    create = mocker.patch("helper.discord_helper.create_discord_scheduled_event")
    response = client.post("/v2/calendar", json=payload(sync_discord=True))
    assert response.get_json()["discord_sync"] == "skipped"
    create.assert_not_called()


def test_create_with_sync_stores_discord_id(client, bot):
    response = client.post("/v2/calendar", json=payload(sync_discord=True))
    body = response.get_json()
    assert response.status_code == 201
    assert body["discord_sync"] == "ok"
    assert body["data"]["discord_event_id"] == "111"
    name, start, end = bot.create.call_args.args
    assert name == "Clan mass"
    assert start == datetime.fromisoformat(payload()["start_date"])


def test_create_without_sync_never_calls_bot(client, bot):
    response = client.post("/v2/calendar", json=payload(sync_discord=False))
    assert response.get_json()["discord_sync"] == "skipped"
    bot.create.assert_not_called()


def test_create_sync_failure_still_saves(client, bot):
    bot.create.return_value = None
    response = client.post("/v2/calendar", json=payload(sync_discord=True))
    assert response.status_code == 201
    assert response.get_json()["discord_sync"] == "failed"
    assert stored_discord_id(response.get_json()["data"]["id"]) is None


def test_past_start_is_nudged_for_discord_only(client, bot):
    started = NOW - timedelta(hours=2)
    response = client.post("/v2/calendar", json=payload(sync_discord=True, start_date=iso(started)))
    _, start, _ = bot.create.call_args.args
    assert start > datetime.now(timezone.utc)
    assert datetime.fromisoformat(response.get_json()["data"]["start_date"]) == started


def test_entry_already_over_is_skipped(client, bot):
    response = client.post("/v2/calendar", json=payload(
        sync_discord=True, start_date=iso(NOW - timedelta(days=3)), end_date=iso(NOW - timedelta(days=2))))
    assert response.get_json()["discord_sync"] == "skipped"
    bot.create.assert_not_called()


def test_update_with_existing_discord_event(client, bot):
    entry_id = make_entry(sync_discord=True, discord_event_id="111")
    response = client.put(f"/v2/calendar/{entry_id}", json=payload(name="Renamed", sync_discord=True))
    assert response.get_json()["discord_sync"] == "ok"
    assert bot.update.call_args.args[:2] == ("111", "Renamed")
    bot.create.assert_not_called()


def test_update_turning_sync_on_creates(client, bot):
    entry_id = make_entry()
    response = client.put(f"/v2/calendar/{entry_id}", json=payload(sync_discord=True))
    assert response.get_json()["discord_sync"] == "ok"
    assert stored_discord_id(entry_id) == "111"


def test_update_recreates_event_deleted_in_discord(client, bot):
    entry_id = make_entry(sync_discord=True, discord_event_id="111")
    bot.update.return_value = "missing"
    bot.create.return_value = "222"
    response = client.put(f"/v2/calendar/{entry_id}", json=payload(sync_discord=True))
    assert response.get_json()["discord_sync"] == "ok"
    assert stored_discord_id(entry_id) == "222"


def test_update_turning_sync_off_deletes(client, bot):
    entry_id = make_entry(sync_discord=True, discord_event_id="111")
    response = client.put(f"/v2/calendar/{entry_id}", json=payload(sync_discord=False))
    assert response.get_json()["discord_sync"] == "ok"
    bot.delete.assert_called_once_with("111")
    assert stored_discord_id(entry_id) is None


def test_update_sync_off_clears_id_even_if_delete_fails(client, bot):
    entry_id = make_entry(sync_discord=True, discord_event_id="111")
    bot.delete.return_value = False
    response = client.put(f"/v2/calendar/{entry_id}", json=payload(sync_discord=False))
    assert response.get_json()["discord_sync"] == "failed"
    assert stored_discord_id(entry_id) is None


def test_delete_removes_discord_event(client, bot):
    entry_id = make_entry(sync_discord=True, discord_event_id="111")
    response = client.delete(f"/v2/calendar/{entry_id}")
    assert response.get_json()["discord_sync"] == "ok"
    bot.delete.assert_called_once_with("111")


def test_delete_without_discord_event_skips(client, bot):
    entry_id = make_entry()
    assert client.delete(f"/v2/calendar/{entry_id}").get_json()["discord_sync"] == "skipped"
    bot.delete.assert_not_called()
