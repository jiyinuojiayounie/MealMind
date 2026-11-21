import json
from pathlib import Path

import pytest

from app.schemas.planning_intent import ConfirmedSafetyConstraints
from app.services.meal_composition import CookingEffortScore, score_cooking_effort
from app.services.planning_intent import PlanningBlocked, PlanningSuccess, extract_planning_intent, plan_from_intent
from app.services.recipe_catalog import DEVELOPMENT_CATALOG_PATH, load_recipe_catalog

CASES_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "planning_intent_v1.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))
DEV_MODE = "development_drafts"


@pytest.fixture(scope="module")
def catalog():
    return load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_planning_intent_case(catalog, case):
    intent = extract_planning_intent(case["text"])
    assert intent.original_text == case["text"]
    assert intent.explicit_fields == frozenset(case["explicit_fields"])
    assert [issue.code for issue in intent.unresolved] == case["issues"]
    assert intent.confirmed_safety is None
    values = intent.model_dump(mode="json")
    values["available_ingredients"] = [
        [item.ingredient_id, item.state] for item in intent.available_ingredients
    ]
    assert {key: values[key] for key in case["expected"]} == case["expected"]

    result = plan_from_intent(catalog, intent, mode=DEV_MODE)
    assert result.status == case["expected_status"]
    if isinstance(result, PlanningSuccess):
        assert all(meal.required_roles <= meal.covered_roles for meal in result.plan.meals)
        assert result.plan.diversity.repeated_recipes == result.plan.diversity.repeated_families == 0
        if intent.scope == "full_day":
            assert [meal.meal_type for meal in result.plan.meals] == ["breakfast", "lunch", "dinner"]
        if intent.scope == "single_dish":
            assert len(result.plan.meals[0].recipes) == 1
        if intent.cooking_time_limit is not None:
            assert all(meal.estimated_total_minutes <= intent.cooking_time_limit for meal in result.plan.meals)
        if intent.ingredient_mode == "strict":
            available = {(item.ingredient_id, item.state) for item in intent.available_ingredients}
            for meal in result.plan.meals:
                for recipe in meal.recipes:
                    assert all((item.ingredient_id, item.state) in available for item in recipe.ingredients)
                    assert not recipe.process_water or ("ingredient_water", "ready_to_use") in available
        if intent.flavor_preference == "mild":
            assert result.unapplied_preferences == ("flavor_preference",)
    elif isinstance(result, PlanningBlocked):
        assert list(result.reasons) == case["reasons"]
    else:
        assert [result.reason] == case["reasons"]


def test_drafts_are_disabled_by_default(catalog):
    intent = extract_planning_intent("Tonight; dinner")
    assert plan_from_intent(catalog, intent).status == "clarification_required"
    intent = extract_planning_intent("Plan dinner")
    assert plan_from_intent(catalog, intent).status == "no_feasible_plan"


def test_one_person_intent_requires_single_serving_catalog_recipes(catalog):
    intent = extract_planning_intent("安排今天三餐，适合一个人做")
    assert intent.scope == "full_day"
    assert intent.servings == 1
    assert intent.cooking_effort_preference == "low"
    assert intent.explicit_fields == {"scope", "servings", "cooking_effort"}
    assert not intent.unresolved

    result = plan_from_intent(catalog, intent, mode=DEV_MODE)
    assert isinstance(result, PlanningSuccess)
    assert not result.unapplied_preferences
    multi_serving_catalog = catalog.model_copy(update={
        "recipes": tuple(recipe.model_copy(update={"servings": 2}) for recipe in catalog.recipes),
    })
    assert plan_from_intent(multi_serving_catalog, intent, mode=DEV_MODE).status == "no_feasible_plan"


def test_convenience_full_day_offline_ranking_comparison(catalog):
    intent = extract_planning_intent("帮我安排今天三餐，适合一个人做，简单省事")
    baseline_intent = intent.model_copy(update={"cooking_effort_preference": None})
    baseline = plan_from_intent(catalog, baseline_intent, mode=DEV_MODE)
    ordinary = plan_from_intent(catalog, extract_planning_intent("安排今天三餐"), mode=DEV_MODE)
    result = plan_from_intent(catalog, intent, mode=DEV_MODE)
    assert isinstance(baseline, PlanningSuccess)
    assert isinstance(ordinary, PlanningSuccess)
    assert isinstance(result, PlanningSuccess)
    assert ordinary.plan == baseline.plan
    assert score_cooking_effort(baseline.plan.meals) == CookingEffortScore(7, 123, 17, 0)
    assert score_cooking_effort(result.plan.meals) == CookingEffortScore(5, 85, 13, 0)
    assert score_cooking_effort(baseline.plan.meals).points == 258
    assert score_cooking_effort(result.plan.meals).points == 184
    assert [meal.composition_type for meal in result.plan.meals] == [
        "main_plus_staple", "main_plus_staple", "single_recipe_complete",
    ]
    assert [meal.composition_type for meal in baseline.plan.meals] == [
        "main_plus_staple", "main_plus_staple", "multi_dish",
    ]
    for plan in (baseline.plan, result.plan):
        assert plan.diversity.repeated_recipes == plan.diversity.repeated_families == 0
        assert all(meal.required_roles <= meal.covered_roles for meal in plan.meals)


def test_polite_prefix_does_not_turn_unrelated_text_into_a_meal_request():
    intent = extract_planning_intent("请帮我整理今天三餐的账单")
    assert "scope" not in intent.explicit_fields
    assert [(issue.code, issue.text) for issue in intent.unresolved] == [
        ("unrecognized_clause", "请帮我整理今天三餐的账单"),
    ]


def test_confirmation_does_not_make_drafts_allergen_safe(catalog):
    intent = extract_planning_intent("Dinner; I am allergic to peanuts")
    assert plan_from_intent(catalog, intent, mode=DEV_MODE).status == "clarification_required"
    confirmed = intent.model_copy(update={
        "confirmed_safety": ConfirmedSafetyConstraints(
            confirmed_statements=frozenset(intent.allergy_statements), excluded_allergens=frozenset({"peanut"})
        )
    })
    assert plan_from_intent(catalog, confirmed, mode=DEV_MODE).status == "no_feasible_plan"


def test_confirmed_dietary_ingredient_exclusion_reaches_engine(catalog):
    intent = extract_planning_intent("Dinner; one dish; no eggs")
    confirmed = intent.model_copy(update={
        "confirmed_safety": ConfirmedSafetyConstraints(
            confirmed_statements=frozenset(intent.dietary_exclusions),
            excluded_ingredient_ids=frozenset({"ingredient_egg"}),
        )
    })
    result = plan_from_intent(catalog, confirmed, mode=DEV_MODE)
    assert isinstance(result, PlanningSuccess)
    assert all(item.ingredient_id != "ingredient_egg" for item in result.plan.meals[0].recipes[0].ingredients)


def test_unconfirmed_second_safety_clause_blocks_planning(catalog):
    intent = extract_planning_intent("Dinner; allergic to peanuts; allergic to eggs")
    partially_confirmed = intent.model_copy(update={
        "confirmed_safety": ConfirmedSafetyConstraints(
            confirmed_statements=frozenset({"allergic to peanuts"}),
            excluded_allergens=frozenset({"peanut"}),
        )
    })
    assert plan_from_intent(catalog, partially_confirmed, mode=DEV_MODE) == PlanningBlocked(
        "clarification_required", ("unconfirmed_allergies",)
    )


def test_non_spicy_constraint_requires_verified_heat_even_in_draft_mode(catalog):
    from datetime import date

    from app.schemas.recipe_catalog import FlavorProfile, ReviewEvidence

    intent = extract_planning_intent("Dinner; one dish; not spicy")
    assert plan_from_intent(catalog, intent, mode=DEV_MODE) == PlanningBlocked(
        "unsupported_constraints", ("unverified_flavor_constraint",)
    )

    evidence = ReviewEvidence(reference="synthetic only", reviewer="fixture", reviewed_on=date(2026, 1, 1))
    recipes = {recipe.recipe_id: recipe for recipe in catalog.recipes}
    verified_non_spicy = recipes["recipe_000010"].model_copy(update={
        "flavor": FlavorProfile(heat="non_spicy", status="verified", basis="Fixture only", evidence=evidence)
    })
    verified_spicy = recipes["recipe_000007"].model_copy(update={
        "flavor": FlavorProfile(heat="spicy", status="verified", basis="Fixture only", evidence=evidence)
    })
    provisional = recipes["recipe_000008"]
    unknown = recipes["recipe_000009"]
    unavailable = catalog.model_copy(update={"recipes": (verified_spicy, provisional, unknown)})
    assert plan_from_intent(unavailable, intent, mode=DEV_MODE).status == "no_feasible_plan"

    test_catalog = catalog.model_copy(update={"recipes": (*unavailable.recipes, verified_non_spicy)})
    result = plan_from_intent(test_catalog, intent, mode=DEV_MODE)
    assert isinstance(result, PlanningSuccess)
    assert result.plan.meals[0].recipes == (verified_non_spicy,)
    assert plan_from_intent(test_catalog, intent).status == "unsupported_constraints"
