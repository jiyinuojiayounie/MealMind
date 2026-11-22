import json
import sqlite3
from contextlib import closing
from decimal import Decimal

import pytest

from app.services.nutrition_reference import load_nutrition_reference

from test_food_logs import DATE, DRAFT, PATH, client_for

VERSION = "usda-sr-legacy-v1"
RAW = "chicken_breast_skinless_boneless_raw"
COOKED = "chicken_breast_meat_stewed"
DAILY = f"/api/v1/nutrition/daily?date={DATE}"


def selected(name, food_id, *, quantity=None, unit=None, method=None, edible=False):
    item = {"name": name, "quantity": quantity, "unit": unit, "preparation_method": method}
    return {**item, "reference_binding": {
        "food_id": food_id, "reference_version": VERSION, "confirmed": True,
        "edible_weight_confirmed": edible, "item": item,
    }}


def create(client, items):
    result = client.post(PATH, json={**DRAFT, "items": items})
    assert result.status_code == 201, result.json()
    return result.json()


def confirm(client, log):
    result = client.post(f"{PATH}/{log['id']}/confirm", json={"expected_revision": log["revision"]})
    assert result.status_code == 200, result.json()
    return result.json()


def test_bound_raw_and_stewed_chicken_through_daily_analysis(tmp_path):
    database = tmp_path / "logs.sqlite3"
    raw = selected("鸡胸肉", RAW, quantity=150, unit="g", edible=True)
    cooked = selected("鸡胸肉", COOKED, quantity=150, unit="g", method="炖", edible=True)
    with client_for(database) as client:
        draft = create(client, [raw, cooked])
        assert draft["description"] == DRAFT["description"]
        assert [item["name"] for item in draft["items"]] == ["鸡胸肉", "鸡胸肉"]
        assert client.get(DAILY).json()["status"] == "no_confirmed_logs"
        for item, state in zip(draft["items"], ["raw", "cooked"], strict=True):
            binding = item["reference_binding"]
            assert binding["state"] == state and binding["fdc_id"] > 0
            assert binding["binding_version"] == "food-reference-binding-v1"
            assert binding["confirmed_at"] and binding["source_release"]
            assert item["quantity"] == 150 and item["unit"] == "g"
        reopened, = client.get(PATH, params={"date": DATE}).json()
        assert reopened == draft
        # Resubmit only the writable selection fields, as the reopened editor does.
        editable = []
        for item in reopened["items"]:
            saved = item["reference_binding"]
            selection = {key: saved[key] for key in raw["reference_binding"]}
            assert selection["edible_weight_confirmed"] is True
            editable.append({**item, "reference_binding": selection})
        update = client.put(f"{PATH}/{draft['id']}", json={
            **DRAFT, "items": editable, "expected_revision": reopened["revision"],
        })
        assert update.status_code == 200, update.json()
        confirmed = confirm(client, update.json())
        assert all(item["reference_binding"]["edible_weight_confirmed"] for item in confirmed["items"])

    with client_for(database) as client:
        assert client.get(PATH, params={"date": DATE}).json() == [confirmed]
        day = client.get(DAILY).json()
        raw_result, cooked_result = day["logs"][0]["items"]
        references = {food.food_id: food for food in load_nutrition_reference().foods}
        for result, food_id in [(raw_result, RAW), (cooked_result, COOKED)]:
            assert result["name"] == "鸡胸肉"
            assert result["status"] == "calculated"
            assert result["provenance"]["food_id"] == food_id
            assert result["provenance"]["fdc_id"] == references[food_id].source.fdc_id
            assert Decimal(result["edible_grams"]) == 150
            for nutrient, value in result["nutrients"].items():
                assert Decimal(value) == getattr(references[food_id].nutrients, nutrient).amount * Decimal("1.5")
        assert raw_result["nutrients"] != cooked_result["nutrients"]
        assert day["day_completeness"] == "not_assessed"
        assert day["item_count"] == day["calculated_item_count"] == 2


def test_portion_evidence_independent_from_confirmed_identity(tmp_path):
    with client_for(tmp_path / "logs.sqlite3") as client:
        draft = create(client, [
            selected("鸡胸肉", RAW),
            selected("糙米饭", "brown_rice_long_grain_cooked", quantity=0.5, unit="碗"),
            selected("鸡胸肉", RAW, quantity=150, unit="g"),
            selected("水煮蛋", "whole_egg_hard_boiled", quantity=1, unit="usda large egg"),
            selected("水煮蛋", "whole_egg_hard_boiled", quantity=1, unit="个"),
            selected("USDA medium peeled banana, length meets USDA standard", "banana_raw", quantity=1, unit="piece"),
        ])
        confirm(client, draft)
        response = client.get(DAILY)
        assert response.status_code == 200, response.json()
        day = response.json()
        items = day["logs"][0]["items"]
        assert day["status"] == "partial" and day["calculated_item_count"] == 2
        for index, reason in [(0, "quantity_unknown"), (1, "unsupported_serving_conversion"),
                              (2, "portion_needs_review"), (4, "unsupported_serving_conversion")]:
            item = items[index]
            assert item["reasons"] == [reason]
            assert item["edible_grams"] is None and item["nutrients"]["energy_kcal"] is None
            assert item["provenance"]["food_id"]
        for index, source_row in [(3, 92500), (5, 93515)]:
            assert items[index]["status"] == "calculated"
            assert items[index]["conversion"] == "reference_portion"
            assert items[index]["provenance"]["portion_source_row_id"] == source_row


@pytest.mark.parametrize(("override", "reason"), [
    ({"food_id": "invented"}, "reference_not_applicable"),
    ({"food_id": "banana_raw"}, "reference_not_applicable"),
    ({"reference_version": "unavailable-v1"}, "catalog_version_unavailable"),
    ({"confirmed": False}, None),
    ({"confirmed": 1}, None),
    ({"fdc_id": 123}, None),
    ({"edible_grams": 130}, None),
    ({"state": "cooked"}, None),
    ({"energy_kcal": 15}, None),
])
def test_rejects_untrusted_or_unavailable_selection(tmp_path, override, reason):
    item = selected("鸡胸肉", RAW, quantity=150, unit="g", edible=True)
    item["reference_binding"].update(override)
    database = tmp_path / "logs.sqlite3"
    with client_for(database) as client:
        response = client.post(PATH, json={**DRAFT, "items": [item]})
        assert response.status_code == 422
        if reason:
            assert response.json()["detail"] == {
                "status": "food_reference_binding_rejected", "item_index": 0, "reason": reason,
            }
    assert not database.exists()


@pytest.mark.parametrize("name,method", [("海南鸡饭", None), ("鸡胸肉", "烤")])
def test_reference_must_be_applicable_to_identity_and_preparation(tmp_path, name, method):
    with client_for(tmp_path / "logs.sqlite3") as client:
        response = client.post(PATH, json={**DRAFT, "items": [selected(name, RAW, method=method)]})
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "reference_not_applicable"


def test_revision_checks_removal_reorder_and_item_changes(tmp_path):
    with client_for(tmp_path / "logs.sqlite3") as client:
        chicken = selected("鸡胸肉", RAW, quantity=150, unit="g", edible=True)
        egg = selected("水煮蛋", "whole_egg_hard_boiled", quantity=1, unit="usda large egg")
        draft = create(client, [chicken, egg])
        path = f"{PATH}/{draft['id']}"
        reordered = client.put(path, json={**DRAFT, "items": [egg, chicken], "expected_revision": 1})
        assert reordered.status_code == 200
        assert [entry["reference_binding"]["food_id"] for entry in reordered.json()["items"]] == ["whole_egg_hard_boiled", RAW]
        assert client.put(path, json={**DRAFT, "items": [egg], "expected_revision": 1}).status_code == 409
        for edited in [
            {**egg, "quantity": 2}, {**egg, "unit": "个"}, {**egg, "name": "鸡胸肉"},
            {**egg, "preparation_method": "raw"},
        ]:
            stale = client.put(path, json={**DRAFT, "items": [edited], "expected_revision": 2})
            assert stale.status_code == 422 and stale.json()["detail"]["reason"] == "item_changed"
        removed = client.put(path, json={**DRAFT, "items": [{"name": "鸡胸肉"}], "expected_revision": 2})
        assert removed.status_code == 200 and "reference_binding" not in removed.json()["items"][0]
        assert confirm(client, removed.json())["revision"] == 4


@pytest.mark.parametrize("fault,reason", [
    ("version", "food_reference_binding_version_unavailable"),
    ("changed", "food_reference_binding_stale"),
    ("fdc_id", "food_reference_binding_invalid"),
    ("malformed", "food_reference_binding_invalid"),
])
def test_unusable_saved_binding_abstains_without_legacy_fallback(tmp_path, fault, reason):
    database = tmp_path / "isolated.sqlite3"
    with client_for(database) as client:
        draft = create(client, [selected("raw pak choi", "bok_choy_raw", quantity=100, unit="g", edible=True)])
        saved = confirm(client, draft)
        with closing(sqlite3.connect(database)) as db, db:
            row = db.execute("SELECT document FROM food_logs WHERE id = ?", (saved["id"],)).fetchone()
            document = json.loads(row[0])
            item = document["items"][0]
            if fault == "version":
                item["reference_binding"]["reference_version"] = "unavailable-v1"
            elif fault == "changed":
                item["quantity"] = 120
            elif fault == "fdc_id":
                item["reference_binding"]["fdc_id"] = 123
            else:
                item["reference_binding"] = {"fdc_id": "invalid"}
            db.execute("UPDATE food_logs SET document = ? WHERE id = ?", (json.dumps(document), saved["id"]))
        before = database.read_bytes()
        day = client.get(DAILY).json()
        result = day["logs"][0]["items"][0]
        assert result["status"] == "not_calculable"
        assert result["reasons"] == [reason]
        assert result["provenance"] is None and result["edible_grams"] is None
        assert reason in day["review_guidance"]
        assert database.read_bytes() == before


def test_legacy_record_calculates_without_rewrite(tmp_path):
    database = tmp_path / "logs.sqlite3"
    with client_for(database) as client:
        saved = confirm(client, create(client, [{"name": "raw pak choi", "quantity": 100, "unit": "g"}]))
        assert "reference_binding" not in saved["items"][0]
        before = database.read_bytes()
        day = client.get(DAILY).json()
        assert day["logs"][0]["items"][0]["status"] == "calculated"
        assert client.get(PATH, params={"date": DATE}).json() == [saved]
        assert database.read_bytes() == before


def test_stale_draft_binding_blocks_confirmation_until_removed(tmp_path, monkeypatch):
    database = tmp_path / "logs.sqlite3"
    with client_for(database) as client:
        draft = create(client, [selected("鸡胸肉", RAW, quantity=150, unit="g", edible=True)])
        log_path = f"{PATH}/{draft['id']}"
        from app.services import food_reference_binding

        original = food_reference_binding.resolve_binding
        monkeypatch.setattr(food_reference_binding, "resolve_binding", lambda *_: (None, "catalog_version_unavailable"))
        before = database.read_bytes()
        rejected = client.post(f"{log_path}/confirm", json={"expected_revision": 1})
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["reason"] == "catalog_version_unavailable"
        assert database.read_bytes() == before
        assert client.get(DAILY).json()["status"] == "no_confirmed_logs"

        monkeypatch.setattr(food_reference_binding, "resolve_binding", original)
        corrected = client.put(log_path, json={
            **DRAFT, "items": [{"name": "鸡胸肉", "quantity": 150, "unit": "g"}], "expected_revision": 1,
        })
        assert corrected.status_code == 200
        assert confirm(client, corrected.json())["status"] == "confirmed"
