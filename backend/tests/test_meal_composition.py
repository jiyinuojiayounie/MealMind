import json
from pathlib import Path

import pytest

from app.schemas.meal_composition import AvailableIngredient, CompositionRequest, MealSlot
from app.services.meal_composition import (
    ComposedPlan,
    MealCombination,
    NoFeasiblePlan,
    compose_plan,
    retrieve_candidates,
    score_cooking_effort,
    score_diversity,
)
from app.services.recipe_catalog import DEVELOPMENT_CATALOG_PATH, load_recipe_catalog

CASES_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "meal_composition_v1.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))
DEV_MODE = "development_drafts"


@pytest.fixture(scope="module")
def catalog():
    return load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)


def as_request(payload):
    return CompositionRequest.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_offline_composition_cases(catalog, case):
    result = compose_plan(catalog, as_request(case["request"]), mode=case["mode"])
    assert result.status == case["expected_status"]
    if isinstance(result, NoFeasiblePlan):
        assert result.reason == case["reason"]
        return

    assert not result.diversity.repeated_recipes
    assert not result.diversity.repeated_families
    assert all(meal.required_roles <= meal.covered_roles for meal in result.meals)
    if "recipe_ids" in case:
        assert [recipe.recipe_id for meal in result.meals for recipe in meal.recipes] == case["recipe_ids"]


def test_strict_availability_distinguishes_process_water(catalog):
    slot = MealSlot(meal_type="dinner", style="single_dish", anchor_recipe_id="recipe_000004")
    fields = {
        "slots": (slot,),
        "strict_ingredients": True,
        "available_ingredients": (AvailableIngredient(ingredient_id="ingredient_sweet_potato", state="raw"),),
    }
    assert isinstance(compose_plan(catalog, CompositionRequest(**fields), mode=DEV_MODE), NoFeasiblePlan)
    allowed = CompositionRequest(**fields, process_water_available=True)
    assert isinstance(compose_plan(catalog, allowed, mode=DEV_MODE), ComposedPlan)


def test_strict_dinner_cannot_invent_missing_seasoning(catalog):
    payload = next(case["request"] for case in CASES if case["id"] == "strict_dinner_with_exact_inventory")
    request = as_request({**payload, "available_ingredients": payload["available_ingredients"][:-1]})
    assert isinstance(compose_plan(catalog, request, mode=DEV_MODE), NoFeasiblePlan)


def test_easy_vegetable_dish_cannot_replace_complete_dinner(catalog):
    recipes = {recipe.recipe_id: recipe for recipe in catalog.recipes}
    cucumber = recipes["recipe_000013"]
    noodle_soup = recipes["recipe_000018"]
    request = CompositionRequest(slots=(MealSlot(meal_type="dinner"),), prefer_low_effort=True)
    small_catalog = catalog.model_copy(update={"recipes": (cucumber, noodle_soup)})
    result = compose_plan(small_catalog, request, mode=DEV_MODE)
    assert cucumber.times.total_minutes < noodle_soup.times.total_minutes
    assert isinstance(result, ComposedPlan)
    assert result.meals[0].recipes == (noodle_soup,)
    assert result.meals[0].composition_type == "single_recipe_complete"
    vegetable_only = small_catalog.model_copy(update={"recipes": (cucumber,)})
    assert compose_plan(vegetable_only, request, mode=DEV_MODE) == NoFeasiblePlan(
        "no_slot_combination", ("dinner",),
    )


def test_effort_counts_declared_prerequisite_without_relaxing_strict_inventory(catalog):
    payload = next(case["request"] for case in CASES if case["id"] == "strict_dinner_with_exact_inventory")
    request = as_request(payload).model_copy(update={"prefer_low_effort": True})
    result = compose_plan(catalog, request, mode=DEV_MODE)
    assert isinstance(result, ComposedPlan)
    effort = score_cooking_effort(result.meals)
    assert (effort.dishes, effort.total_minutes, effort.distinct_ingredients, effort.prerequisites) == (1, 16, 5, 1)
    assert (effort.heated_components, effort.equipment_load, effort.points) == (1, 2, 59)
    assert not effort.meets_simple_meal_target
    no_cooked_rice = request.model_copy(update={"available_ingredients": tuple(
        item for item in request.available_ingredients if item.ingredient_id != "ingredient_rice"
    )})
    assert isinstance(compose_plan(catalog, no_cooked_rice, mode=DEV_MODE), NoFeasiblePlan)


def test_sequence_time_includes_all_dishes(catalog):
    selected = tuple(recipe for recipe in catalog.recipes if recipe.recipe_id in {"recipe_000008", "recipe_000014"})
    small_catalog = catalog.model_copy(update={"recipes": selected})
    slots = (MealSlot(meal_type="dinner"),)
    too_short = CompositionRequest(slots=slots, max_total_minutes_per_meal=46)
    enough = CompositionRequest(slots=slots, max_total_minutes_per_meal=47)
    assert isinstance(compose_plan(small_catalog, too_short, mode=DEV_MODE), NoFeasiblePlan)
    result = compose_plan(small_catalog, enough, mode=DEV_MODE)
    assert isinstance(result, ComposedPlan)
    assert result.meals[0].estimated_total_minutes == 47


def test_retrieval_filters_roles_dietary_and_explicit_exclusions(catalog):
    slots = (MealSlot(meal_type="dinner"),)
    request = CompositionRequest(slots=slots, excluded_ingredient_ids=frozenset({"ingredient_egg"}))
    candidates = retrieve_candidates(catalog, request, "dinner", roles=frozenset({"protein"}), mode=DEV_MODE)
    assert candidates and all("protein" in recipe.dish_roles for recipe in candidates)
    assert all(item.ingredient_id != "ingredient_egg" for recipe in candidates for item in recipe.ingredients)

    dietary = CompositionRequest(slots=slots, required_dietary_tags=frozenset({"vegetarian"}))
    assert not retrieve_candidates(catalog, dietary, "dinner", mode=DEV_MODE)


def test_unresolved_exclusion_fails_closed(catalog):
    request = CompositionRequest(
        slots=(MealSlot(meal_type="dinner"),),
        excluded_ingredient_ids=frozenset({"ingredient_not_in_catalog"}),
    )
    assert compose_plan(catalog, request, mode=DEV_MODE) == NoFeasiblePlan("unresolved_constraints")


def test_diversity_scores_recipe_family_ingredients_and_methods(catalog):
    recipes = {recipe.recipe_id: recipe for recipe in catalog.recipes}
    egg = recipes["recipe_000008"]
    other_egg = recipes["recipe_000002"]
    fish = recipes["recipe_000005"]
    same_family = other_egg.model_copy(update={"dish_family_id": egg.dish_family_id})

    def combination(recipe, meal_type):
        return MealCombination(
            meal_type, (recipe,), frozenset(), frozenset(recipe.dish_roles), recipe.times.total_minutes
        )

    breakfast = combination(egg, "breakfast")
    duplicate = score_diversity((breakfast, combination(egg, "dinner")))
    family = score_diversity((breakfast, combination(same_family, "dinner")))
    repeated_ingredient = score_diversity((breakfast, combination(other_egg, "dinner")))
    varied = score_diversity((breakfast, combination(fish, "dinner")))
    assert (duplicate.repeated_recipes, duplicate.repeated_families) == (1, 1)
    assert (family.repeated_recipes, family.repeated_families) == (0, 1)
    assert repeated_ingredient.repeated_primary_ingredients == 1
    assert varied.points > repeated_ingredient.points > family.points > duplicate.points
    assert varied.distinct_methods == 2
    assert varied.distinct_compositions == 2


def test_plan_ranking_is_stable_when_catalog_order_changes(catalog):
    request = CompositionRequest(slots=tuple(
        MealSlot(meal_type=kind) for kind in ("breakfast", "lunch", "dinner")
    ))
    plan = compose_plan(catalog, request, mode=DEV_MODE)
    reordered = catalog.model_copy(update={"recipes": tuple(reversed(catalog.recipes))})
    assert plan == compose_plan(reordered, request, mode=DEV_MODE)
    assert isinstance(plan, ComposedPlan)
    assert plan.diversity.repeated_primary_ingredients == 0


def test_catalog_preserves_recorded_times_and_draft_prerequisites(catalog):
    selected = {int(recipe.recipe_id.split("_")[1]): recipe for recipe in catalog.recipes}
    steam_eggs = selected[2]
    assert steam_eggs.process_water.purpose == "steam"
    assert steam_eggs.process_water.quantity_ml is None
    assert any(item.ingredient_id == "ingredient_water" and item.quantity == 120 for item in steam_eggs.ingredients)
    for recipe in (selected[16], selected[17]):
        rice = next(item for item in recipe.ingredients if item.ingredient_id == "ingredient_rice")
        assert rice.state == "cooked" and rice.required_starting_state
    original = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH.with_name("catalog-v1.json"))
    def recorded_minutes(snapshot):
        return [
            (
                recipe.times.preparation_minutes, recipe.times.cooking_minutes,
                recipe.times.waiting_minutes, recipe.times.total_minutes,
            )
            for recipe in snapshot.recipes
        ]

    before = recorded_minutes(original)
    after = recorded_minutes(catalog)
    assert after[:13] == before[:13] and after[14:20] == before[14:]
    assert after[13] == (6, 21, 5, 32)
    assert all(recipe.review.status == "draft" for recipe in catalog.recipes)


def test_available_recent_family_can_be_avoided_without_losing_dinner_roles(catalog):
    request = CompositionRequest(slots=(MealSlot(meal_type="dinner"),))
    original = compose_plan(catalog, request, mode=DEV_MODE)
    recent = {recipe.dish_family_id for recipe in original.meals[0].recipes}
    alternative = compose_plan(catalog, request, mode=DEV_MODE, recent_family_ids=recent)
    assert not recent.intersection(recipe.dish_family_id for recipe in alternative.meals[0].recipes)
    assert {"protein", "staple", "vegetable"} <= alternative.meals[0].covered_roles
