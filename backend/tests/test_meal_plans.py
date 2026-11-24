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
    "user_request": "One dish for dinner; make tomato eggs with 番茄 and eggs.",
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


def _complete_day(sample):
    meals = []
    for kind, title, names in (
        ("breakfast", "Egg toast", ("eggs", "toast")),
        ("lunch", "Tofu rice bowl", ("tofu", "rice", "bok choy")),
        ("dinner", "Tomato egg noodles", ("番茄", "eggs", "noodles")),
    ):
        meals.append({
            "meal_type": kind, "estimated_preparation_minutes": 12,
            "dishes": [{"name": title, "instructions": ["Cook together."], "ingredients": [
                {"name": name, "quantity": 1, "unit": "serving"} for name in names
            ]}],
        })
    sample["meals"] = meals


def test_flexible_full_day(api, gemini, plan):
    _complete_day(plan)
    gemini[1].return_value = SimpleNamespace(text=json.dumps(plan))

    response = api.post(PATH, json={
        **PAYLOAD, "scope": "full_day", "meal_type": None, "ingredient_mode": "flexible",
        "available_ingredients": [" EGGS "], "language": "zh-CN",
    })

    assert response.status_code == 200
    assert response.json()["additional_ingredients"] == ["toast", "tofu", "rice", "bok choy", "番茄", "noodles"]
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
    _complete_day(plan)
    gemini[1].return_value = SimpleNamespace(text=json.dumps(plan))
    response = api.post(PATH + query, json={
        "user_request": "Plan breakfast, lunch and dinner.",
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


def test_single_dish_without_sides_is_accepted_without_retry(api, gemini, plan):
    plan["meals"][0]["dishes"][0]["ingredients"] = [{"name": "番茄", "quantity": 100, "unit": "g"}]
    gemini[1].return_value = SimpleNamespace(text=json.dumps(plan))
    response = api.post(PATH, json={**PAYLOAD, "user_request": "One dish for dinner"})
    assert response.status_code == 200
    gemini[1].assert_called_once()


@pytest.mark.parametrize(("failure", "stage"), [
    ("single_slot", "scope_validation"), ("late_dinner", "time_validation"),
    ("weak_roles", "accepted"), ("broken_json", "response_schema"), (None, "accepted"),
])
def test_stabilization_trace_distinguishes_first_time_prompt_outcomes(gemini, plan, failure, stage):
    from scripts.smoke_live_planning import SMOKE_REQUEST

    _complete_day(plan)
    if failure == "single_slot":
        plan["meals"] = plan["meals"][-1:]
    elif failure == "late_dinner":
        plan["meals"][-1]["estimated_preparation_minutes"] = 21
    elif failure == "weak_roles":
        plan["meals"][-1]["dishes"][0]["ingredients"] = [{"name": "番茄", "quantity": 100, "unit": "g"}]
    gemini[1].return_value = SimpleNamespace(text="{" if failure == "broken_json" else json.dumps(plan))
    app = create_app(Settings(_env_file=None, environment="development", gemini_diagnostics=True, GEMINI_API_KEY="test-key"))
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 51000)) as client:
        response = client.post(PATH + "?infer_scope=true", json={
            "user_request": SMOKE_REQUEST, "scope": "single_meal", "language": "zh-CN", "ingredient_mode": "flexible",
        })
        traces = client.get("/api/v1/meal-plans/local-traces")
    assert response.status_code == (502 if stage != "accepted" else 200)
    assert traces.headers["Cache-Control"] == "no-store"
    trace, = traces.json()
    assert trace["request_id"] == response.headers["X-Request-ID"]
    assert trace["stage"] == stage and trace["full_day_required"]
    assert trace["slot_limits"] == {"lunch": 20, "dinner": 20}
    assert SMOKE_REQUEST not in traces.text and "test-key" not in traces.text
    gemini[1].assert_called_once()


def test_local_planning_trace_is_unavailable_outside_development():
    with TestClient(create_app(Settings(_env_file=None, gemini_diagnostics=True))) as client:
        assert client.get("/api/v1/meal-plans/local-traces").status_code == 404


@pytest.mark.parametrize(("variant", "status", "stage"), [
    ("observed", 200, "accepted"),
    ("complete", 200, "accepted"),
    ("single_slot", 502, "scope_validation"),
])
def test_generate_todays_three_meals_with_browser_defaults(gemini, plan, variant, status, stage):
    _complete_day(plan)
    for meal, name, ingredients in zip(
        plan["meals"],
        ("葱花鸡蛋饼", "香菇青菜焖饭", "豆腐皮炒西葫芦"),
        (
            ["鸡蛋", "面粉", "小葱", "食用油"],
            ["大米", "鲜香菇", "上海青", "生抽"],
            ["豆腐皮", "西葫芦", "大蒜", "食用油"],
        ),
        strict=True,
    ):
        if variant == "complete":
            ingredients += {"lunch": ["鸡蛋"], "dinner": ["米饭"]}.get(meal["meal_type"], [])
        meal["dishes"][0].update(
            name=name,
            ingredients=[{"name": ingredient, "quantity": 30, "unit": "克"} for ingredient in ingredients],
        )
    if variant == "single_slot":
        plan["meals"] = plan["meals"][:1]
    gemini[1].return_value = SimpleNamespace(text=json.dumps(plan))
    app = create_app(Settings(_env_file=None, environment="development", gemini_diagnostics=True, GEMINI_API_KEY="test-key"))
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 51000)) as client:
        response = client.post(PATH + "?infer_scope=true", json={
            "user_request": "帮我生成今天的一日三餐",
            "scope": "single_meal",
            "language": "zh-CN",
            "ingredient_mode": "flexible",
        })
        trace, = client.get("/api/v1/meal-plans/local-traces").json()

    assert response.status_code == status
    assert trace["request_id"] == response.headers["X-Request-ID"]
    assert trace["stage"] == stage
    assert trace["full_day_required"] is True
    if status == 200:
        assert [meal["meal_type"] for meal in response.json()["meals"]] == ["breakfast", "lunch", "dinner"]
        assert trace["blocking_quality_issues"] == []
    if variant == "observed":
        assert trace["quality_issues"] == ["missing_complete_meal_roles"]
        assert trace["missing_roles_by_meal"] == {"lunch": ["protein"], "dinner": ["staple"]}
    if variant == "complete":
        assert trace["missing_roles_by_meal"] == {}
    gemini[1].assert_called_once()
    assert "explicitly requires breakfast, lunch, and dinner" in gemini[1].call_args.kwargs["config"].system_instruction


@pytest.mark.parametrize(("outcome", "status", "stage", "attempts"), [
    ("recovered", 200, "accepted", 2),
    ("exhausted", 503, "provider_http", 2),
    ("invalid_key", 502, "provider_http", 1),
    ("quality", 502, "quality_validation", 1),
    ("malformed", 502, "response_schema", 1),
])
def test_planning_api_retries_only_provider_503(gemini, monkeypatch, plan, outcome, status, stage, attempts):
    backoff = MagicMock()
    monkeypatch.setattr(meal_plans, "sleep", backoff)
    unavailable = errors.ServerError(503, {"error": {"message": "private-provider-detail"}})
    valid = SimpleNamespace(text=json.dumps(plan))
    if outcome == "recovered":
        effects = [unavailable, valid]
    elif outcome == "exhausted":
        effects = [unavailable, unavailable]
    elif outcome == "invalid_key":
        effects = [errors.ClientError(401, {"error": {"message": "Invalid API key: private-provider-detail"}})]
    elif outcome == "quality":
        effects = [SimpleNamespace(text=json.dumps(plan))]
    else:
        effects = [SimpleNamespace(text="{")]
    factory, generate = gemini
    generate.side_effect = effects
    settings = Settings(_env_file=None, environment="development", gemini_diagnostics=True, GEMINI_API_KEY="test-key")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000", client=("127.0.0.1", 51000)) as client:
        payload = {**PAYLOAD, "user_request": "Vegan dinner"} if outcome == "quality" else PAYLOAD
        response = client.post(PATH, json=payload)
        traces = client.get("/api/v1/meal-plans/local-traces")
    trace, = traces.json()

    assert response.status_code == status
    assert trace["request_id"] == response.headers["X-Request-ID"]
    assert trace["stage"] == stage
    assert trace["provider_attempts"] == generate.call_count == attempts
    factory.assert_called_once()
    assert factory.call_args.kwargs["http_options"].retry_options.attempts == 1
    if attempts == 2:
        assert trace["provider_retry_status"] == 503
        assert generate.call_args_list[0] == generate.call_args_list[1]
        backoff.assert_called_once_with(0.5)
    else:
        backoff.assert_not_called()
    if outcome == "exhausted":
        assert trace["provider_status"] == 503
        assert response.json()["detail"] == "Meal planning is currently unavailable."
    elif outcome == "invalid_key":
        assert trace["provider_status"] == 401
    assert "private-provider-detail" not in response.text + traces.text


@pytest.mark.parametrize(("text", "reason"), [
    ("晚餐，我对花生过敏", "dietary_restriction_unverified"),
    ("Vegan dinner without peanuts, preferably within 15 minutes", "dietary_restriction_unverified"),
    ("只用鸡蛋。只用番茄。", "ingredient_restriction_unverified"),
    ("Plan a full day within 20 minutes", "time_limit_unverified"),
])
def test_unverified_hard_constraint_stops_before_provider(api, gemini, text, reason):
    response = api.post(PATH + "?infer_scope=true", json={
        **PAYLOAD, "meal_type": None, "user_request": text,
    })
    assert response.status_code == 422
    assert response.json()["detail"]["status"] == reason
    gemini[0].assert_not_called()


@pytest.mark.parametrize("text", ["晚餐只用番茄", "晚餐10分钟以内", "Dinner in no more than 10 minutes"])
def test_recognized_text_only_hard_requirements_still_block(api, gemini, plan, text):
    gemini[1].return_value = SimpleNamespace(text=json.dumps(plan))
    response = api.post(PATH, json={
        **PAYLOAD, "user_request": text, "ingredient_mode": "flexible", "cooking_time_limit": None,
    })
    assert response.status_code == 502
    gemini[1].assert_called_once()
