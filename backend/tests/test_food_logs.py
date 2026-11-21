import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

PATH = "/api/v1/food-logs"
DATE = "2026-11-21"
DRAFT = {
    "consumed_at": "2026-11-21T00:15:00+08:00",
    "description": "  Rice and steamed egg  ",
    "items": [{"name": "Rice", "quantity": 1, "unit": "bowl"},
              {"name": "Egg", "preparation_method": "steamed"}],
}


def client_for(path, *, environment="development", peer="127.0.0.1", server="127.0.0.1", **settings):
    return TestClient(
        create_app(Settings(_env_file=None, environment=environment, food_log_db_path=path, **settings)),
        base_url=f"http://{server}:8000",
        client=(peer, 50000),
    )


def test_food_log_lifecycle_across_app_restarts(tmp_path):
    database = tmp_path / "local" / "logs.sqlite3"
    with client_for(database) as client:
        created = client.post(PATH, json=DRAFT)
        assert created.status_code == 201
        draft = created.json()
        assert draft["status"] == "draft"
        assert draft["source"] == "manual_text"
        assert draft["meal_type"] == "unspecified"
        assert draft["revision"] == 1
        assert draft["description"] == DRAFT["description"]
        assert draft["items"][1]["quantity"] is None
        assert draft["items"][1]["unit"] is None
        assert draft["created_at"] == draft["updated_at"]
        assert client.get(PATH, params={"date": "2026-11-20"}).json() == []

    log_path = f"{PATH}/{draft['id']}"
    with client_for(database) as client:
        assert client.get(PATH, params={"date": DATE}).json() == [draft]
        corrected = client.put(log_path, json={
            **DRAFT, "meal_type": "breakfast", "consumed_at": "2026-11-22T00:10:00+08:00",
            "expected_revision": 1,
        })
        assert corrected.status_code == 200
        assert corrected.json()["revision"] == 2
        assert corrected.json()["created_at"] == draft["created_at"]
        assert client.get(PATH, params={"date": DATE}).json() == []
        assert client.post(f"{log_path}/confirm", json={"expected_revision": 1}).status_code == 409
        confirmed = client.post(f"{log_path}/confirm", json={"expected_revision": 2})
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"
        assert confirmed.json()["revision"] == 3
        assert confirmed.json()["meal_type"] == "breakfast"
        assert client.post(f"{log_path}/confirm", json={"expected_revision": 2}).json() == confirmed.json()
        assert client.put(log_path, json={**DRAFT, "expected_revision": 3}).status_code == 409
        assert client.delete(log_path, params={"expected_revision": 2}).status_code == 409

    with client_for(database) as client:
        assert client.get(PATH, params={"date": "2026-11-22"}).json() == [confirmed.json()]
        assert client.delete(log_path, params={"expected_revision": 3}).status_code == 204
        assert client.delete(log_path, params={"expected_revision": 3}).status_code == 404
        assert client.get(PATH, params={"date": "2026-11-22"}).json() == []


def test_simultaneous_confirmation_is_idempotent(tmp_path):
    with client_for(tmp_path / "logs.sqlite3") as client:
        draft = client.post(PATH, json=DRAFT).json()

        def confirm():
            return client.post(f"{PATH}/{draft['id']}/confirm", json={"expected_revision": 1})

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = [result.result() for result in (pool.submit(confirm), pool.submit(confirm))]
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert first.json()["revision"] == 2
        assert client.get(PATH, params={"date": DATE}).json() == [first.json()]


@pytest.mark.parametrize("overrides", [
    {"status": "confirmed"},
    {"source": "unknown"},
    {"meal_type": "brunch"},
    {"description": "  "},
    {"consumed_at": "2026-11-21T00:15:00"},
    {"consumed_at": 1795210500},
    {"items": []},
    {"items": [{"name": " "}]},
    {"items": [{"name": "Rice", "quantity": 0}]},
    {"items": [{"name": "Rice", "quantity": -1}]},
    {"items": [{"name": "Rice", "quantity": "1"}]},
    {"items": [{"name": "Rice", "quantity": True}]},
])
def test_invalid_drafts_are_rejected(tmp_path, overrides):
    with client_for(tmp_path / "logs.sqlite3") as client:
        assert client.post(PATH, json={**DRAFT, **overrides}).status_code == 422
        assert client.get(PATH, params={"date": DATE}).json() == []
        assert client.get(PATH, params={"date": "2026-02-30"}).status_code == 422


@pytest.mark.parametrize("settings,headers,status", [
    ({"environment": "production"}, {}, 404),
    ({"peer": "192.0.2.1"}, {"X-Forwarded-For": "127.0.0.1"}, 403),
    ({"server": "192.0.2.1"}, {"Host": "localhost:8000"}, 403),
    ({}, {"Host": "untrusted.example:8000"}, 403),
    ({"cors_origins": ["https://untrusted.example"]}, {"Origin": "https://untrusted.example"}, 403),
])
def test_non_local_requests_do_not_create_storage(tmp_path, settings, headers, status):
    database = tmp_path / "logs.sqlite3"
    with client_for(database, **settings) as client:
        assert client.post(PATH, json=DRAFT, headers=headers).status_code == status
        assert client.get(PATH, params={"date": DATE}, headers=headers).status_code == status
    assert not database.exists()


def test_loopback_browser_origin_and_local_preflight(tmp_path):
    with client_for(tmp_path / "logs.sqlite3") as client:
        headers = {"Origin": "http://localhost:5173"}
        preflight = client.options(PATH, headers={**headers, "Access-Control-Request-Method": "PUT",
                                                  "Access-Control-Request-Headers": "content-type"})
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == headers["Origin"]
        assert client.post(PATH, json=DRAFT, headers=headers).status_code == 201


def test_newer_database_schema_is_not_changed(tmp_path):
    database = tmp_path / "newer.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA user_version = 99")
    with client_for(database) as client:
        assert client.post(PATH, json=DRAFT).status_code == 503
        assert client.get(PATH, params={"date": DATE}).status_code == 503
    with sqlite3.connect(database) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (99,)
