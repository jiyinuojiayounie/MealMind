import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app
from app.schemas.meal_plans import MealPlanResponse
from app.services import meal_plans
from app.services.recipe_catalog import DEVELOPMENT_CATALOG_PATH, load_recipe_catalog

PATH = "/api/v1/meal-plans/generate"
CATALOG_PATH = PATH + "?planning_mode=catalog"
FULL_DAY_REQUEST = "帮我安排今天三餐，适合一个人做，简单省事"
BASE = {
    "user_request": "Plan dinner",
    "language": "en-US",
    "scope": "single_meal",
    "ingredient_mode": "flexible",
}
LOCAL = {
    "environment": "development",
    "catalog_planning_enabled": True,
    "catalog_use_drafts": True,
}


@pytest.fixture(autouse=True)
def gemini(monkeypatch):
    factory = MagicMock()
    generate = factory.return_value.__enter__.return_value.models.generate_content
    generate.side_effect = AssertionError("No model call expected")
    monkeypatch.setattr(meal_plans.genai, "Client", factory)
    return factory, generate


def api(*, client_ip="127.0.0.1", server="127.0.0.1", **overrides):
    return TestClient(
        create_app(Settings(_env_file=None, GEMINI_API_KEY="test key", **overrides)),
        base_url=f"http://{server}:8000",
        client=(client_ip, 50000),
    )


def test_complete_dinner_reconstructs_catalog_dishes(gemini):
    with api(**LOCAL) as client:
        response = client.post(CATALOG_PATH, json=BASE)

    assert response.status_code == 200
    result = MealPlanResponse.model_validate(response.json())
    catalog = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)
    recipes = {r.names.en_us: r for r in catalog.recipes}
    ingredients = {i.ingredient_id: i.names.en_us for i in catalog.ingredients}
    meal = result.meals[0]
    selected = [recipes[dish.name] for dish in meal.dishes]
    assert {"protein", "staple", "vegetable"} <= {role for r in selected for role in r.dish_roles}
    assert meal.estimated_preparation_minutes == sum(r.times.total_minutes for r in selected)
    for dish, recipe in zip(meal.dishes, selected, strict=True):
        assert [(item.name, item.quantity, item.unit) for item in dish.ingredients] == [
            (ingredients[item.ingredient_id], item.quantity, item.unit) for item in recipe.ingredients
        ]
        assert dish.instructions[-len(recipe.steps.en_us):] == list(recipe.steps.en_us)
    assert "Local draft" in result.explanation
    gemini[0].assert_not_called()


def test_full_day_is_unique_by_recipe_and_family(gemini):
    with api(**LOCAL) as client:
        response = client.post(CATALOG_PATH + "&infer_scope=true", json={
            **BASE, "user_request": "安排今天三餐", "language": "zh-CN",
        })

    assert response.status_code == 200
    result = MealPlanResponse.model_validate(response.json())
    assert [meal.meal_type for meal in result.meals] == ["breakfast", "lunch", "dinner"]
    catalog = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)
    recipes = {r.names.zh_cn: r for r in catalog.recipes}
    selected = [recipes[dish.name] for meal in result.meals for dish in meal.dishes]
    assert len(selected) == len({r.recipe_id for r in selected}) == len({r.dish_family_id for r in selected})
    gemini[0].assert_not_called()


@pytest.mark.parametrize("prompt,ranks_for_effort", [
    (FULL_DAY_REQUEST, True),
    ("安排今天三餐，适合一个人做，简单省事", True),
    ("帮我安排今天三餐", False),
    ("安排今天三餐，简单省事", True),
    ("请帮我安排今天的早午晚餐", False),
    ("今天三餐", False),
])
def test_conversational_full_day_reaches_composition(gemini, prompt, ranks_for_effort):
    with api(**LOCAL, catalog_personalization=ranks_for_effort) as client:
        response = client.post(CATALOG_PATH + "&infer_scope=true", json={
            **BASE, "user_request": prompt, "language": "zh-CN",
        })

    assert response.status_code == 200
    result = MealPlanResponse.model_validate(response.json())
    assert [meal.meal_type for meal in result.meals] == ["breakfast", "lunch", "dinner"]
    assert ("只能部分满足这一偏好" in result.explanation) is ranks_for_effort
    assert "部分偏好尚无法应用" not in result.explanation
    gemini[0].assert_not_called()


def test_convenience_dinner_explanation_in_english(gemini):
    with api(**LOCAL, catalog_personalization=False) as client:
        response = client.post(CATALOG_PATH, json={**BASE, "user_request": "Plan dinner; 简单省事"})

    assert response.status_code == 200
    result = MealPlanResponse.model_validate(response.json())
    assert "Ranked for easier preparation using catalog estimates." in result.explanation
    gemini[0].assert_not_called()


@pytest.mark.parametrize("suffix,infer_scope,code,status,reason", [
    ("，每餐5分钟以内", True, 409, "no_feasible_plan", "no_slot_combination"),
    ("，5分钟以内", True, 422, "clarification_required", "ambiguous_time_scope"),
    ("，我对花生过敏", True, 422, "clarification_required", "unconfirmed_allergies"),
    ("，别碰带壳海鲜", True, 422, "clarification_required", "unrecognized_clause"),
    ("，我只有鸡蛋和番茄", True, 409, "no_feasible_plan", "no_slot_combination"),
    ("", False, 422, "clarification_required", "conflicting_values"),
])
def test_conversational_full_day_preserves_constraints(gemini, suffix, infer_scope, code, status, reason):
    path = CATALOG_PATH + "&infer_scope=true" if infer_scope else CATALOG_PATH
    with api(**LOCAL, catalog_personalization=False) as client:
        response = client.post(path, json={**BASE, "user_request": FULL_DAY_REQUEST + suffix, "language": "zh-CN"})

    assert response.status_code == code
    detail = response.json()["detail"]
    assert detail["status"] == status
    assert reason in detail.get("reasons", [detail.get("reason")])
    gemini[0].assert_not_called()


def test_strict_food_and_time_limits_preserve_exact_catalog_plan(gemini):
    with api(**LOCAL) as client:
        response = client.post(CATALOG_PATH, json={
            **BASE, "user_request": "Plan dinner; within 20 minutes", "ingredient_mode": "existing",
            "available_ingredients": ["cooked rice", "eggs", "bok choy", "cooking oil", "salt"],
            "cooking_time_limit": 16,
        })

    assert response.status_code == 200
    result = MealPlanResponse.model_validate(response.json())
    assert result.additional_ingredients == []
    assert result.meals[0].estimated_preparation_minutes == 16
    assert [dish.name for dish in result.meals[0].dishes] == ["Egg and bok choy fried rice"]
    gemini[0].assert_not_called()


@pytest.mark.parametrize("text,updates,code,status,reason", [
    ("Dinner; allergic to peanuts", {}, 422, "clarification_required", "unconfirmed_allergies"),
    ("Dinner; not spicy", {}, 422, "unsupported_constraints", "unverified_flavor_constraint"),
    ("Tonight with the usual restrictions", {}, 422, "clarification_required", "unrecognized_clause"),
    ("I only have eggs and tomatoes", {"available_ingredients": ["eggs", "tomatoes", "cooking oil"]},
     422, "clarification_required", "conflicting_values"),
    ("Dinner", {"meal_type": "lunch"}, 422, "clarification_required", "conflicting_values"),
    ("Plan a full day", {}, 422, "clarification_required", "conflicting_values"),
    ("Within 20 minutes", {"scope": "full_day"}, 422, "clarification_required", "ambiguous_time_scope"),
    ("Dinner; within 5 minutes", {}, 409, "no_feasible_plan", "no_slot_combination"),
    ("I only have eggs and tomatoes", {}, 409, "no_feasible_plan", "no_slot_combination"),
])
def test_constraint_outcomes_never_call_provider(gemini, text, updates, code, status, reason):
    with api(**LOCAL, catalog_personalization=True) as client:
        response = client.post(CATALOG_PATH, json={**BASE, "user_request": text, **updates})
    assert response.status_code == code
    detail = response.json()["detail"]
    assert detail["status"] == status
    assert reason in detail.get("reasons", [detail.get("reason")])
    gemini[0].assert_not_called()


@pytest.mark.parametrize("settings,client_ip,server,code,status", [
    ({}, "127.0.0.1", "127.0.0.1", 403, "catalog_disabled"),
    ({"catalog_planning_enabled": True}, "127.0.0.1", "127.0.0.1", 409, "no_feasible_plan"),
    ({"catalog_planning_enabled": True, "catalog_use_drafts": True},
     "127.0.0.1", "127.0.0.1", 403, "draft_catalog_forbidden"),
    (LOCAL, "192.0.2.1", "127.0.0.1", 403, "draft_catalog_forbidden"),
    (LOCAL, "127.0.0.1", "192.0.2.1", 403, "draft_catalog_forbidden"),
])
def test_catalog_mode_and_draft_access_gates(gemini, settings, client_ip, server, code, status):
    with api(client_ip=client_ip, server=server, **settings) as client:
        response = client.post(CATALOG_PATH, json=BASE)

    assert response.status_code == code
    assert response.json()["detail"]["status"] == status
    gemini[0].assert_not_called()


def test_model_can_select_only_ranked_plan_and_does_not_receive_raw_text(gemini):
    _, generate = gemini
    generate.side_effect = None
    generate.return_value = SimpleNamespace(text='{"candidate_id":"candidate_2","reason":"catalog_match"}')

    with api(**LOCAL, catalog_personalization=True) as client:
        response = client.post(CATALOG_PATH, json=BASE)

    assert response.status_code == 200
    generate.assert_called_once()
    sent = json.loads(generate.call_args.kwargs["contents"])
    assert "user_request" not in sent and "Plan dinner" not in str(sent)
    second = sent["candidates"][1]
    assert second["id"] == "candidate_2"
    assert response.json()["meals"][0]["estimated_preparation_minutes"] == second["meals"][0]["estimated_minutes"]
    assert [dish["name"] for dish in response.json()["meals"][0]["dishes"]] == [
        recipe["name"] for recipe in second["meals"][0]["recipes"]
    ]


@pytest.mark.parametrize("selection", [
    {"candidate_id": "recipe_000018", "reason": "catalog_match"},
    {"candidate_id": "candidate_1", "reason": "catalog_match", "recipe_ids": ["recipe_999999"]},
    {"candidate_id": "candidate_1", "reason": "catalog_match", "calories": 123},
    {"candidate_id": "candidate_1", "reason": "a free text nutrition claim"},
])
def test_invalid_provider_selection_has_no_fallback(gemini, selection):
    _, generate = gemini
    generate.side_effect = None
    generate.return_value = SimpleNamespace(text=json.dumps(selection))
    with api(**LOCAL, catalog_personalization=True) as client:
        response = client.post(CATALOG_PATH, json=BASE)

    assert response.status_code == 502
    generate.assert_called_once()


def test_prompt_only_remains_default_with_catalog_enabled(gemini):
    _, generate = gemini
    generate.side_effect = None
    generate.return_value = SimpleNamespace(text=json.dumps({
        "title": "Baseline",
        "meals": [{
            "meal_type": "dinner",
            "estimated_preparation_minutes": 10,
            "dishes": [{
                "name": "Baseline dish",
                "ingredients": [{"name": "Water", "quantity": 1, "unit": "cup"}],
                "instructions": ["Example baseline instruction."],
            }],
        }],
        "explanation": "Baseline explanation.",
    }))
    with api(**LOCAL) as client:
        response = client.post(PATH, json=BASE)

    assert response.status_code == 200
    assert response.json()["title"] == "Baseline"
    assert json.loads(generate.call_args.kwargs["contents"])["user_request"] == BASE["user_request"]


def test_process_water_is_explained_separately_from_consumed_ingredients(gemini):
    with api(**LOCAL) as client:
        response = client.post(CATALOG_PATH, json={
            **BASE, "user_request": "Breakfast; one dish; within 17 minutes",
            "ingredient_mode": "existing",
            "available_ingredients": ["eggs", "water", "salt", "scallion"],
        })

    assert response.status_code == 200
    result = response.json()
    dish = result["meals"][0]["dishes"][0]
    assert dish["name"] == "Steamed eggs with scallion"
    assert any("separate process water" in step for step in dish["instructions"])
    assert [item["quantity"] for item in dish["ingredients"] if item["name"] == "Water"] == [120]
    assert not result["additional_ingredients"]
    gemini[0].assert_not_called()


def test_model_cannot_choose_candidate_id_absent_from_shortlist(gemini):
    _, generate = gemini
    generate.side_effect = None
    generate.return_value = SimpleNamespace(text='{"candidate_id":"candidate_3","reason":"catalog_match"}')
    with api(**LOCAL, catalog_personalization=True) as client:
        response = client.post(CATALOG_PATH, json={
            **BASE, "user_request": "Dinner; one dish; within 16 minutes",
            "ingredient_mode": "existing",
            "available_ingredients": ["eggs", "tomatoes", "cooking oil", "salt", "bok choy", "garlic"],
        })
    assert response.status_code == 502
    assert len(json.loads(generate.call_args.kwargs["contents"])["candidates"]) == 2
    generate.assert_called_once()


def test_full_day_rejects_distinct_ids_from_same_family(monkeypatch, gemini):
    from app.api import meal_plans as route

    catalog = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)
    by_id = {recipe.recipe_id: recipe for recipe in catalog.recipes}
    first = by_id["recipe_000016"]
    second = by_id["recipe_000018"].model_copy(update={"dish_family_id": first.dish_family_id})
    equivalent_families = catalog.model_copy(update={
        "recipes": (by_id["recipe_000001"], by_id["recipe_000002"], first, second),
    })
    monkeypatch.setattr(route, "load_recipe_catalog", lambda _: equivalent_families)
    with api(**LOCAL) as client:
        response = client.post(CATALOG_PATH, json={
            **BASE, "user_request": "Plan a full day", "scope": "full_day",
            "available_ingredients": ["cooked rice"],
        })

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "no_distinct_day"
    gemini[0].assert_not_called()
