import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from google.genai import errors

from app.core.settings import Settings
from app.main import create_app
from app.services import meal_plans

CONTEXT = "/api/v1/replan/context"
PREVIEW = "/api/v1/replan/preview"
LOGS = "/api/v1/food-logs"
ZONE = "Asia/Singapore"
TODAY = datetime.now(ZoneInfo(ZONE)).date()
DATE = TODAY.isoformat()
PRIVATE = "PRIVATE_DESCRIPTION_FIXTURE"


@pytest.fixture(autouse=True)
def gemini(monkeypatch):
    client = MagicMock()
    generate = client.return_value.__enter__.return_value.models.generate_content
    generate.side_effect = AssertionError("No real provider call")
    monkeypatch.setattr(meal_plans.genai, "Client", client)
    return generate


def api(path, *, environment="development", peer="127.0.0.1", **settings):
    return TestClient(create_app(Settings(
        _env_file=None, environment=environment, food_log_db_path=path, GEMINI_API_KEY="test-key", **settings,
    )), base_url="http://127.0.0.1:8000", client=(peer, 50000))


def log(client, meal_type, *, name="青菜", quantity=None, confirmed=True, timestamp=None):
    payload = {
        "meal_type": meal_type, "description": PRIVATE,
        "consumed_at": timestamp or f"{DATE}T12:00:00+08:00",
        "items": [{"name": name, "quantity": quantity, "unit": "g"}],
    }
    response = client.post(LOGS, json=payload)
    assert response.status_code == 201
    body = response.json()
    if not confirmed:
        return body
    response = client.post(f"{LOGS}/{body['id']}/confirm", json={"expected_revision": body["revision"]})
    assert response.status_code == 200
    return response.json()


def context(client, day=DATE):
    response = client.get(CONTEXT, params={"date": day})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert PRIVATE not in response.text
    return response.json()


def payload(client, **updates):
    return {
        "date": DATE, "timezone": ZONE, "target_meal_type": "dinner",
        "expected_context_fingerprint": context(client)["context_fingerprint"],
        "constraints": {"restriction_status": "none_declared", "language": "en-US"}, **updates,
    }


def plan(*slots):
    return {
        "title": "Meal fixture", "explanation": "Simple meal", "meals": [{
            "meal_type": slot, "estimated_preparation_minutes": 15,
            "dishes": [{"name": slot, "ingredients": [{"name": "Rice", "quantity": 1, "unit": "g"}],
                        "instructions": ["Cook the rice."]}],
        } for slot in slots],
    }


def respond(gemini, *slots):
    gemini.side_effect = None
    gemini.return_value = SimpleNamespace(text=json.dumps(plan(*slots)))


def test_empty_context_and_standalone_catalog_preview_do_not_create_db(tmp_path, gemini):
    database = tmp_path / "never-created.sqlite3"
    with api(database, catalog_planning_enabled=True, catalog_use_drafts=True, catalog_personalization=True) as client:
        previous = context(client)
        response = client.post(PREVIEW, json=payload(client, planning_mode="catalog"))
    assert previous["locked_meal_types"] == [] and previous["confirmed_log_count"] == 0
    assert previous["remaining_main_meal_types"] == ["breakfast", "lunch", "dinner"]
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["current_meal"] is None and result["base_plan_revision"] is None
    assert result["status"] == "preview" and result["source"] == "catalog"
    assert [part["meal_type"] for part in result["suggested_plan"]["meals"]] == ["dinner"]
    gemini.assert_not_called()
    assert not database.exists()


def test_existing_plan_only_targets_dinner_and_uses_confirmed_variety(tmp_path, gemini):
    database = tmp_path / "logs.sqlite3"
    respond(gemini, "dinner")
    with api(database) as client:
        log(client, "breakfast", name="葱花蒸蛋")
        log(client, "lunch", name="熟长粒糙米", quantity=150)
        log(client, "dinner", confirmed=False)
        assert client.get("/api/v1/nutrition/daily", params={"date": DATE}).json()["status"] == "partial"
        saved = {"plan_id": str(uuid4()), "revision": 3, "date": DATE, "source": "prompt_only",
                 "plan": {**plan("breakfast", "lunch", "dinner"), "additional_ingredients": []}}
        bytes_before = database.read_bytes()
        response = client.post(PREVIEW, json=payload(client, current_plan=saved))
        assert database.read_bytes() == bytes_before
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["context"]["locked_meal_types"] == ["breakfast", "lunch"]
    assert result["current_meal"] == saved["plan"]["meals"][2]
    assert result["untouched_meal_types"] == ["breakfast", "lunch"]
    assert result["base_plan_revision"] == 3 and result["base_plan_id"] == saved["plan_id"]
    assert result["context_fingerprint"] == result["context"]["context_fingerprint"]
    assert result["variety_match_count"] == 1
    assert "nutrition_coverage_not_used" in result["uncertainty"]
    assert PRIVATE not in response.text
    gemini.assert_called_once()
    provider = gemini.call_args.kwargs
    assert PRIVATE not in provider["contents"] and "熟长粒糙米" not in provider["contents"]
    assert json.loads(provider["contents"])["earlier_foods_for_variety"] == ["Steamed eggs with scallion"]
    assert json.loads(provider["contents"])["meal_type"] == "dinner"


def test_draft_and_unspecified_do_not_lock_slot_or_invent_history(tmp_path, gemini):
    respond(gemini, "lunch")
    with api(tmp_path / "logs.sqlite3") as client:
        log(client, "lunch", confirmed=False)
        log(client, "unspecified")
        assert client.get("/api/v1/nutrition/daily", params={"date": DATE}).json()["status"] == "not_calculable"
        value = context(client)
        response = client.post(PREVIEW, json=payload(client, target_meal_type="lunch"))
    assert value["confirmed_log_count"] == 1 and value["unspecified_log_count"] == 1
    assert value["locked_meal_types"] == []
    assert response.status_code == 200
    assert response.json()["variety_match_count"] == 0


def test_confirmed_and_earlier_unknown_slots_are_ineligible(tmp_path, gemini):
    with api(tmp_path / "logs.sqlite3") as client:
        log(client, "lunch")
        for target, status in [("lunch", "meal_slot_completed"), ("breakfast", "meal_slot_not_remaining")]:
            result = client.post(PREVIEW, json=payload(client, target_meal_type=target))
            assert result.status_code == 409 and result.json()["detail"]["status"] == status
        log(client, "dinner")
        assert context(client)["remaining_main_meal_types"] == []
    gemini.assert_not_called()


def test_context_midnight_uses_recorded_offsets_and_deleted_logs_disappear(tmp_path):
    prior = (TODAY - timedelta(days=1)).isoformat()
    with api(tmp_path / "logs.sqlite3") as client:
        log(client, "breakfast", timestamp=f"{DATE}T00:00:00+08:00")
        log(client, "lunch", timestamp=f"{prior}T23:59:59-08:00")
        deleted = log(client, "dinner", timestamp=f"{DATE}T23:59:59-08:00")
        assert context(client)["locked_meal_types"] == ["breakfast", "dinner"]
        assert client.delete(f"{LOGS}/{deleted['id']}", params={"expected_revision": deleted["revision"]}).status_code == 204
        assert context(client)["locked_meal_types"] == ["breakfast"]
        assert context(client, prior)["locked_meal_types"] == ["lunch"]


@pytest.mark.parametrize("constraints,instructions,status,reason", [
    ({}, "", "clarification_required", "review_dietary_restrictions"),
    ({"restriction_status": "present"}, "", "unsupported_constraints", "dietary_restrictions_unverified"),
    ({"restriction_status": "none_declared"}, "I am allergic to peanuts", "unsupported_constraints", "dietary_restrictions_unverified"),
    ({"restriction_status": "none_declared"}, "skip dinner", "clarification_required", "unrecognized_clause"),
    ({"restriction_status": "none_declared"}, "plan a full day", "clarification_required", "conflicting_values"),
])
def test_unchecked_restrictions_or_instructions_do_not_call_gemini(tmp_path, gemini, constraints, instructions, status, reason):
    with api(tmp_path / "logs.sqlite3") as client:
        response = client.post(PREVIEW, json=payload(client, constraints=constraints, instructions=instructions))
    assert response.status_code == 422
    assert response.json()["detail"] == {"status": status, "reasons": [reason]}
    gemini.assert_not_called()


def test_stale_context_before_and_after_the_single_provider_call(tmp_path, gemini):
    database = tmp_path / "logs.sqlite3"
    with api(database) as client:
        old = payload(client)
        log(client, "breakfast")
        result = client.post(PREVIEW, json=old)
        assert result.status_code == 409 and result.json()["detail"]["status"] == "stale_context"
        gemini.assert_not_called()

        def changed(**kwargs):
            log(client, "lunch")
            return SimpleNamespace(text=json.dumps(plan("dinner")))

        gemini.side_effect = changed
        result = client.post(PREVIEW, json=payload(client))
        assert result.status_code == 409 and result.json()["detail"]["status"] == "stale_context"
    gemini.assert_called_once()


def test_prompt_mode_preserves_structured_constraints_and_enforces_exact_target(tmp_path, gemini):
    respond(gemini, "dinner")
    with api(tmp_path / "logs.sqlite3") as client:
        request = payload(client, constraints={
            "restriction_status": "none_declared", "language": "en-US",
            "ingredient_mode": "existing", "available_ingredients": ["Rice"],
            "cooking_time_limit": 20, "prefer_low_effort": True,
        }, instructions="within 15 minutes")
        response = client.post(PREVIEW, json=request)
        assert response.status_code == 200, response.text
        contents = json.loads(gemini.call_args.kwargs["contents"])
        assert contents["available_ingredients"] == ["Rice"]
        assert contents["cooking_time_limit"] == 15
        assert "简单省事" in contents["user_request"]

        gemini.reset_mock()
        respond(gemini, "dinner", "lunch")
        response = client.post(PREVIEW, json=request)
        assert response.status_code == 502
        gemini.assert_called_once()


def test_preview_rejects_punitive_or_invented_nutrition_claims(tmp_path, gemini):
    gemini.side_effect = None
    gemini.return_value = SimpleNamespace(text=json.dumps({
        **plan("dinner"), "explanation": "You ate 1500 kcal. Skip dinner.",
    }))
    with api(tmp_path / "logs.sqlite3") as client:
        assert client.post(PREVIEW, json=payload(client)).status_code == 502
    gemini.assert_called_once()


def test_invalid_dates_and_timezone_are_rejected_with_no_provider_call(tmp_path, gemini):
    with api(tmp_path / "logs.sqlite3") as client:
        assert client.get(CONTEXT, params={"date": "20261122"}).status_code == 422
        rejected = client.post(PREVIEW, json=payload(client, timezone="Invalid/Timezone"))
        assert rejected.json()["detail"]["status"] == "invalid_timezone"
        past = client.post(PREVIEW, json=payload(client, date=(TODAY - timedelta(days=1)).isoformat()))
        assert past.status_code == 409 and past.json()["detail"]["status"] == "date_not_today"
    gemini.assert_not_called()


def test_payload_validation_is_bounded_and_does_not_echo_private_content(tmp_path, gemini):
    with api(tmp_path / "logs.sqlite3") as client:
        invalid_plan = {"plan_id": str(uuid4()), "revision": 3, "date": DATE, "source": "prompt_only",
                        "plan": {**plan("dinner", "dinner"), "additional_ingredients": [], "private": PRIVATE}}
        invalid = client.post(PREVIEW, json=payload(client, current_plan=invalid_plan))
        assert invalid.status_code == 422 and PRIVATE not in invalid.text
        large = client.post(PREVIEW, json=payload(client, instructions="x" * 300_000))
        assert large.status_code == 413
    gemini.assert_not_called()


@pytest.mark.parametrize("error,code", [
    (TimeoutError(PRIVATE), 504),
    (errors.ClientError(400, {"error": {"message": PRIVATE}}), 502),
])
def test_provider_errors_are_redacted_and_not_retried(tmp_path, gemini, error, code):
    gemini.side_effect = error
    with api(tmp_path / "logs.sqlite3") as client:
        response = client.post(PREVIEW, json=payload(client))
        assert response.status_code == code and PRIVATE not in response.text
    gemini.assert_called_once()


@pytest.mark.parametrize("environment,peer,status", [("production", "127.0.0.1", 404), ("development", "192.0.2.1", 403)])
def test_replan_routes_preserve_local_access_boundary(tmp_path, gemini, environment, peer, status):
    database = tmp_path / "logs.sqlite3"
    with api(database, environment=environment, peer=peer) as client:
        assert client.get(CONTEXT, params={"date": DATE}).status_code == status
        assert client.post(PREVIEW, json={}).status_code == status
    assert not database.exists()
    gemini.assert_not_called()
