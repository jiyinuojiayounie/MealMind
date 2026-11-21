import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2
import pytest
from fastapi.testclient import TestClient
from google.genai import errors

from app.core.settings import Settings
from app.main import create_app
from app.schemas.meal_plans import MealPlanResponse
from app.services import meal_plans

PATH = "/api/v1/meal-plans/generate"
PAYLOAD = {
    "user_request": "Make dinner with 番茄 and eggs.",
    "language": "en-US",
    "scope": "single_meal",
    "meal_type": "dinner",
    "available_ingredients": ["番茄", "eggs"],
    "ingredient_mode": "existing",
    "cooking_time_limit": 15,
}


@pytest.fixture
def plan():
    return {
        "title": "Tomato eggs",
        "meals": [{
            "meal_type": "dinner",
            "dishes": [{
                "name": "Tomato eggs",
                "ingredients": [
                    {"name": "番茄", "quantity": 1, "unit": "piece"},
                    {"name": "eggs", "quantity": 2, "unit": "pieces"},
                ],
                "instructions": ["Simmer the chopped tomato and cook the eggs through."],
            }],
            "estimated_preparation_minutes": 12,
        }],
        "explanation": "Uses the ingredients on hand and takes under 15 minutes.",
    }


@pytest.fixture
def gemini(monkeypatch):
    client = MagicMock()
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(meal_plans.genai, "Client", factory)
    return factory, client.models.generate_content


@pytest.fixture
def api(gemini):
    settings = Settings(_env_file=None, GEMINI_API_KEY="fictional-key", GEMINI_MODEL="test-model")
    with TestClient(create_app(settings)) as client:
        yield client


def test_existing_meal(api, gemini, plan):
    factory, generate = gemini
    generate.return_value = SimpleNamespace(text=json.dumps(plan))

    response = api.post(PATH, json=PAYLOAD)

    assert response.status_code == 200
    parsed = MealPlanResponse.model_validate(response.json())
    assert parsed.title == "Tomato eggs"
    assert parsed.additional_ingredients == []
    factory.assert_called_once()
    assert factory.call_args.kwargs["http_options"].retry_options.attempts == 1
    generate.assert_called_once()
    args = generate.call_args.kwargs
    assert args["model"] == "test-model"
    assert json.loads(args["contents"]) == PAYLOAD
    assert args["config"].response_mime_type == "application/json"
    assert args["config"].response_json_schema["required"] == ["title", "meals", "explanation"]


def test_flexible_full_day(api, gemini, plan):
    plan["meals"] = [
        {**plan["meals"][0], "meal_type": meal_type}
        for meal_type in ("breakfast", "lunch", "dinner")
    ]
    gemini[1].return_value = SimpleNamespace(text=json.dumps(plan))

    response = api.post(PATH, json={
        **PAYLOAD, "scope": "full_day", "meal_type": None, "ingredient_mode": "flexible",
        "available_ingredients": [" EGGS "], "language": "zh-CN",
    })

    assert response.status_code == 200
    assert response.json()["additional_ingredients"] == ["番茄"]
    assert json.loads(gemini[1].call_args.kwargs["contents"])["language"] == "zh-CN"


@pytest.mark.parametrize("changes", [
    {"user_request": " "},
    {"language": "en"},
    {"scope": "full_day"},
    {"scope": "weekly"},
    {"meal_type": "brunch"},
    {"available_ingredients": []},
    {"cooking_time_limit": 0},
    {"cooking_time_limit": "15"},
    {"ingredient_mode": "update"},
])
def test_invalid_input(api, gemini, changes):
    assert api.post(PATH, json={**PAYLOAD, **changes}).status_code == 422
    gemini[0].assert_not_called()


def test_missing_configuration(gemini):
    settings = Settings(_env_file=None, GEMINI_API_KEY=None)
    with TestClient(create_app(settings)) as client:
        response = client.post(PATH, json=PAYLOAD)

    assert response.status_code == 503
    gemini[0].assert_not_called()


@pytest.mark.parametrize("error,status", [
    (errors.ClientError(429, {"error": {"message": "fictional-key"}}), 502),
    (errors.ServerError(500, {"error": {"message": "fictional-key"}}), 502),
    (httpx2.ConnectError("fictional-key"), 502),
    (httpx2.ReadTimeout("fictional-key"), 504),
])
def test_provider_failure(api, gemini, error, status):
    gemini[1].side_effect = error
    response = api.post(PATH, json=PAYLOAD)

    assert response.status_code == status
    assert "fictional-key" not in response.text
    gemini[1].assert_called_once()


@pytest.mark.parametrize("error", ["invalid JSON", "missing ingredients", "unlisted ingredient", "wrong type", "too slow"])
def test_invalid_model_output(api, gemini, plan, error):
    meal = plan["meals"][0]
    if error == "missing ingredients":
        meal["dishes"][0]["ingredients"] = []
    elif error == "unlisted ingredient":
        meal["dishes"][0]["ingredients"][0]["name"] = "oil"
    elif error == "wrong type":
        meal["meal_type"] = "lunch"
    elif error == "too slow":
        meal["estimated_preparation_minutes"] = 20

    gemini[1].return_value = SimpleNamespace(
        text=error if error == "invalid JSON" else json.dumps(plan)
    )
    assert api.post(PATH, json=PAYLOAD).status_code == 502


def test_reads_gemini_environment_file(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=fictional-key\nGEMINI_MODEL=test-model\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.gemini_api_key is not None
    assert settings.gemini_model == "test-model"
    assert "fictional-key" not in repr(settings)


def test_provider_schema_preserves_shape_without_generation_bounds():
    from app.schemas.meal_plans import GeneratedMealPlan

    schema = meal_plans._provider_schema()

    assert schema["properties"]["meals"]["items"] == {"$ref": "#/$defs/PlannedMeal"}
    assert "maxItems" not in schema["properties"]["meals"]
    assert "minItems" not in schema["$defs"]["Dish"]["properties"]["ingredients"]
    assert "minimum" not in schema["$defs"]["Ingredient"]["properties"]["quantity"]
    assert GeneratedMealPlan.model_json_schema()["properties"]["meals"]["maxItems"] == 4


@pytest.mark.parametrize("enabled", [True, False])
def test_provider_diagnostics_are_sanitized(gemini, caplog, enabled):
    gemini[1].side_effect = errors.ClientError(400, {
        "error": {"message": "Schema too complex. Authorization: Bearer private-test-data"}
    })
    settings = Settings(
        _env_file=None, GEMINI_API_KEY="fictional-key", gemini_diagnostics=enabled
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(PATH, json=PAYLOAD)

    assert response.status_code == 502
    assert "schema" not in response.text.casefold()
    assert "private-test-data" not in caplog.text
    assert "fictional-key" not in caplog.text
    assert ("Gemini upstream HTTP 400: Structured output schema" in caplog.text) is enabled


@pytest.mark.parametrize("query,meal_type,expected", [
    ("?infer_scope=true", None, 200),
    ("", None, 502),
    ("?infer_scope=true", "dinner", 502),
])
def test_inferred_scope_is_opt_in_and_respects_explicit_meal_type(
    api, gemini, plan, query, meal_type, expected
):
    plan["meals"] = [
        {**plan["meals"][0], "meal_type": kind}
        for kind in ("breakfast", "lunch", "dinner")
    ]
    gemini[1].return_value = SimpleNamespace(text=json.dumps(plan))
    response = api.post(PATH + query, json={
        "user_request": "Plan breakfast, lunch and dinner using only tofu and water.",
        "language": "en-US",
        "scope": "single_meal",
        "meal_type": meal_type,
        "ingredient_mode": "flexible",
    })

    assert response.status_code == expected
    gemini[1].assert_called_once()
    call = gemini[1].call_args.kwargs
    assert ("scope in this request is a fallback" in call["config"].system_instruction) == (expected == 200)
    assert "only when the user's requirements permit them" in call["config"].system_instruction
    assert json.loads(call["contents"])["available_ingredients"] == []
