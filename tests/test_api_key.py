import pytest
import app as app_module
from app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_module, "API_KEYS", ["site-key", "bot-key"])
    return app.test_client()


def test_missing_key_is_rejected(client):
    response = client.get("/users")
    assert response.status_code == 401


def test_wrong_key_is_rejected(client):
    response = client.get("/users", headers={"X-API-Key": "nope"})
    assert response.status_code == 401


def test_any_configured_key_is_accepted(client):
    # An unknown route gets past the key check and 404s without touching the db
    for key in ("site-key", "bot-key"):
        response = client.get("/does-not-exist", headers={"X-API-Key": key})
        assert response.status_code == 404


def test_docs_and_preflight_are_exempt(client):
    assert client.get("/docs/").status_code == 200
    assert client.options("/users").status_code != 401


def test_check_disabled_without_keys(monkeypatch):
    monkeypatch.setattr(app_module, "API_KEYS", [])
    response = app.test_client().get("/does-not-exist")
    assert response.status_code == 404
