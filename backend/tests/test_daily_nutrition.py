import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app
from app.schemas.nutrition_reference import NutritionReference
from app.services import nutrition_calculation
from app.services.nutrition_reference import load_nutrition_reference

LOGS = "/api/v1/food-logs"
DAILY = "/api/v1/nutrition/daily"
DATE = "2026-11-21"
RICE = {"name": "熟长粒糙米", "quantity": 150, "unit": "g"}
EGG = {"name": "全熟白煮蛋（去壳）", "quantity": 1, "unit": "USDA large egg"}
PRIVATE_DESCRIPTION = "private food log fixture text"


def client_for(path, *, environment="development", peer="127.0.0.1"):
    return TestClient(
        create_app(Settings(_env_file=None, environment=environment, food_log_db_path=path)),
        base_url="http://127.0.0.1:8000", client=(peer, 50000),
    )


def create_log(client, items, *, at="2026-11-21T12:00:00+08:00", confirm=True):
    response = client.post(LOGS, json={
        "description": PRIVATE_DESCRIPTION, "consumed_at": at, "items": items, "meal_type": "lunch",
    })
    assert response.status_code == 201
    log = response.json()
    return confirm_log(client, log) if confirm else log


def confirm_log(client, log):
    response = client.post(f"{LOGS}/{log['id']}/confirm", json={"expected_revision": log["revision"]})
    assert response.status_code == 200
    return response.json()


def read_day(client, date=DATE):
    response = client.get(DAILY, params={"date": date})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert PRIVATE_DESCRIPTION not in response.text
    return response.json()


def test_only_live_confirmed_logs_are_counted_once_with_stable_ids_and_provenance(tmp_path):
    with client_for(tmp_path / "logs.sqlite3") as client:
        first = create_log(client, [RICE, EGG], at="2026-11-21T10:00:00+08:00", confirm=False)
        confirmed = confirm_log(client, first)
        assert confirm_log(client, first) == confirmed
        second = create_log(client, [RICE], at="2026-11-21T11:00:00+08:00")
        create_log(client, [EGG], confirm=False)
        deleted = create_log(client, [EGG])
        assert client.delete(f"{LOGS}/{deleted['id']}", params={"expected_revision": deleted["revision"]}).status_code == 204
        result = read_day(client)

    assert result["date"] == DATE and result["date_basis"] == "recorded_offset"
    assert result["status"] == "all_logged_items_calculated"
    assert result["day_completeness"] == "not_assessed"
    assert result["confirmed_log_count"] == 2
    assert result["item_count"] == result["calculated_item_count"] == result["fully_calculated_item_count"] == 3
    assert result["uncalculated_item_count"] == 0
    assert result["reference_version"] == "usda-sr-legacy-v1"
    assert result["reference_source"]["release"] == "2018-04"
    assert result["calculation_version"] == "nutrition-v1"
    assert {key: value["subtotal"] for key, value in result["nutrients"].items()} == {
        "energy_kcal": "446.50", "protein_g": "14.510", "carbohydrate_g": "77.300", "fat_g": "8.215",
    }
    assert all(n["contributing_items"] == 3 and n["missing_items"] == 0 for n in result["nutrients"].values())
    assert [log["log_id"] for log in result["logs"]] == [confirmed["id"], second["id"]]
    first_analysis = result["logs"][0]
    assert first_analysis["revision"] == confirmed["revision"]
    assert first_analysis["consumed_at"] == confirmed["consumed_at"]
    assert first_analysis["summary"]["nutrients"]["energy_kcal"]["subtotal"] == "262.00"
    assert [item["item_index"] for item in first_analysis["items"]] == [0, 1]
    provenance = first_analysis["items"][0]["provenance"]
    assert provenance["fdc_id"] == 169704 and provenance["state"] == "cooked"
    assert provenance["nutrient_source_row_ids"]["energy_kcal"] == 1462903
    assert provenance["source_url"].endswith("/169704/nutrients")
    assert first_analysis["items"][1]["provenance"]["portion_source_row_id"] == 92500


def test_empty_day_and_confirmed_items_without_estimates_have_distinct_status(tmp_path):
    database = tmp_path / "unused" / "logs.sqlite3"
    with client_for(database) as client:
        empty = read_day(client)
        assert empty["status"] == "no_confirmed_logs" and empty["confirmed_log_count"] == 0
        assert empty["logs"] == [] and not database.parent.exists()
        create_log(client, [{"name": "青菜"}])
        unavailable = read_day(client)
    assert unavailable["status"] == "not_calculable"
    assert unavailable["confirmed_log_count"] == unavailable["uncalculated_item_count"] == 1
    assert unavailable["logs"][0]["items"][0]["reasons"] == ["ambiguous_food_match", "quantity_unknown"]
    assert "quantity_unknown" in unavailable["review_guidance"]
    for entry in (empty, unavailable):
        assert entry["day_completeness"] == "not_assessed"
        assert all(n["subtotal"] is None and n["contributing_items"] == 0 for n in entry["nutrients"].values())


def test_partial_coverage_uses_only_estimable_items(tmp_path):
    with client_for(tmp_path / "logs.sqlite3") as client:
        create_log(client, [RICE, {**RICE, "quantity": None}, {"name": "豆腐", "quantity": 80, "unit": "g"}])
        result = read_day(client)
    assert result["status"] == result["logs"][0]["summary"]["status"] == "partial"
    assert result["calculated_item_count"] == 1 and result["uncalculated_item_count"] == 2
    assert result["nutrients"]["energy_kcal"] == {
        "unit": "kcal", "subtotal": "184.50", "contributing_items": 1, "missing_items": 2,
    }
    assert result["logs"][0]["items"][1]["reasons"] == ["quantity_unknown"]
    assert result["logs"][0]["items"][2]["reasons"] == ["ambiguous_food_match"]


def test_date_follows_each_offset_and_agrees_with_food_log_listing(tmp_path):
    with client_for(tmp_path / "logs.sqlite3") as client:
        early = create_log(client, [RICE], at="2026-11-21T00:00:00+08:00")
        late = create_log(client, [RICE], at="2026-11-21T23:59:59-08:00")
        before = create_log(client, [RICE], at="2026-11-20T23:59:59-08:00")
        after = create_log(client, [RICE], at="2026-11-22T00:00:00+08:00")
        original = client.get(LOGS, params={"date": DATE}).json()
        assert [entry["log_id"] for entry in read_day(client)["logs"]] == [log["id"] for log in original]
        assert [entry["log_id"] for entry in read_day(client)["logs"]] == [early["id"], late["id"]]
        assert [entry["log_id"] for entry in read_day(client, "2026-11-20")["logs"]] == [before["id"]]
        assert [entry["log_id"] for entry in read_day(client, "2026-11-22")["logs"]] == [after["id"]]


def test_missing_nutrient_and_real_zero_keep_separate_coverage(tmp_path, monkeypatch):
    data = load_nutrition_reference().model_dump()
    # Synthetic reference values used only in this isolated test.
    row = next(row for row in data["foods"] if row["food_id"] == "brown_rice_long_grain_cooked")
    row["nutrients"]["protein_g"] = None
    row["nutrients"]["carbohydrate_g"]["amount"] = 0
    reference = NutritionReference.model_validate(data)
    monkeypatch.setattr(nutrition_calculation, "load_nutrition_reference", lambda: reference)
    with client_for(tmp_path / "logs.sqlite3") as client:
        create_log(client, [RICE])
        result = read_day(client)
    assert result["status"] == "partial" and result["fully_calculated_item_count"] == 0
    assert result["calculated_item_count"] == 1
    assert result["nutrients"]["protein_g"] == {
        "unit": "g", "subtotal": None, "contributing_items": 0, "missing_items": 1,
    }
    carb = result["nutrients"]["carbohydrate_g"]
    assert float(carb["subtotal"]) == 0 and carb["contributing_items"] == 1 and carb["missing_items"] == 0
    assert result["logs"][0]["items"][0]["reasons"] == ["nutrient_data_missing"]


@pytest.mark.parametrize("date", [None, "", "2026-2-3", "2026-02-30", "20261121", "2026-W47-6", "1795210500",
                                 "2026-11-21T00:00:00+08:00", "2026-11-21 "])
def test_date_query_is_strict(tmp_path, date):
    with client_for(tmp_path / "logs.sqlite3") as client:
        response = client.get(DAILY, params={} if date is None else {"date": date})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "date"]


@pytest.mark.parametrize("environment,peer,headers,status", [
    ("production", "127.0.0.1", {}, 404),
    ("development", "192.0.2.1", {"X-Forwarded-For": "127.0.0.1"}, 403),
    ("development", "127.0.0.1", {"Origin": "https://untrusted.example"}, 403),
])
def test_route_is_local_development_only(tmp_path, environment, peer, headers, status):
    database = tmp_path / "logs.sqlite3"
    with client_for(database, environment=environment, peer=peer) as client:
        assert client.get(DAILY, params={"date": DATE}, headers=headers).status_code == status
        if environment == "production":
            assert DAILY not in client.get("/openapi.json").json()["paths"]
    assert not database.exists()


def test_analysis_opens_database_read_only_and_does_not_touch_records(tmp_path, monkeypatch):
    database = tmp_path / "logs with ? and #.sqlite3"
    with client_for(database) as client:
        original = create_log(client, [RICE])
        before = database.read_bytes()
        timestamp = database.stat().st_mtime_ns
        connect = sqlite3.connect
        opened = []

        def require_read_only(filename, **kwargs):
            opened.append(filename)
            assert kwargs["uri"] is True and filename.endswith("?mode=ro")
            return connect(filename, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(sqlite3, "connect", require_read_only)
            assert read_day(client) == read_day(client)
        assert len(opened) == 2
        assert database.read_bytes() == before and database.stat().st_mtime_ns == timestamp
        assert list(tmp_path.iterdir()) == [database]
        assert client.get(LOGS, params={"date": DATE}).json() == [original]


def test_old_database_is_not_migrated_by_analysis(tmp_path):
    database = tmp_path / "logs.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unversioned (id INT)")
    before = database.read_bytes()
    with client_for(database) as client:
        response = client.get(DAILY, params={"date": DATE})
    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "nutrition_unavailable"
    assert database.read_bytes() == before


def test_corrupt_records_and_reference_errors_do_not_leak_details(tmp_path, monkeypatch, caplog):
    database = tmp_path / "private-path.sqlite3"
    with client_for(database) as client:
        log = create_log(client, [RICE])
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE food_logs SET document = ? WHERE id = ?", ('"private fixture"', log["id"]))
        result = client.get(DAILY, params={"date": DATE})
    assert result.status_code == 503
    assert result.headers["Cache-Control"] == "no-store"
    assert result.json()["detail"]["status"] == "nutrition_unavailable"
    assert "private" not in result.text + caplog.text

    def missing_reference():
        raise OSError("private path to missing reference")

    monkeypatch.setattr(nutrition_calculation, "load_nutrition_reference", missing_reference)
    with client_for(tmp_path / "empty.sqlite3") as client:
        result = client.get(DAILY, params={"date": DATE})
    assert result.status_code == 503 and "private" not in result.text + caplog.text
