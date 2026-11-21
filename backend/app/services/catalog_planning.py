import json
from typing import Literal

from pydantic import ValidationError

from app.core.settings import Settings
from app.schemas.meal_plans import Dish, Ingredient, MealPlanRequest, MealPlanResponse, PlannedMeal, StructuredOutput
from app.schemas.planning_intent import IntentIssue, PlanningIntent
from app.schemas.recipe_catalog import LocalizedText, RecipeCatalog
from app.services.meal_composition import CatalogMode, ComposedPlan, NoFeasiblePlan, score_cooking_effort
from app.services.meal_plans import PlannerFailure, generate_structured
from app.services.planning_intent import (
    PlanningBlocked,
    PlanningSuccess,
    extract_planning_intent,
    plan_from_intent,
    resolve_inventory_labels,
)

SelectionReason = Literal["catalog_match", "varied_methods"]


class CandidateSelection(StructuredOutput):
    candidate_id: Literal["candidate_1", "candidate_2", "candidate_3"]
    reason: SelectionReason


def merge_planning_request(payload: MealPlanRequest, *, infer_scope: bool) -> PlanningIntent:
    intent = extract_planning_intent(payload.user_request)
    issues = list(intent.unresolved)
    fields = set(intent.explicit_fields)
    scope = intent.scope
    if payload.scope == "full_day":
        if ("scope" in fields and scope != "full_day") or "meal_type" in fields:
            issues.append(IntentIssue(code="conflicting_values", text="scope"))
        scope = "full_day"
        fields.add("scope")
    elif scope == "full_day" and not (infer_scope and payload.meal_type is None):
        issues.append(IntentIssue(code="conflicting_values", text="scope"))

    meal_type = intent.meal_type
    if payload.meal_type is not None:
        if "meal_type" in fields and meal_type != payload.meal_type:
            issues.append(IntentIssue(code="conflicting_values", text="meal_type"))
        meal_type = payload.meal_type
        fields.add("meal_type")

    strict = payload.ingredient_mode == "existing" or intent.ingredient_mode == "strict"
    structured_inventory = resolve_inventory_labels(payload.available_ingredients, issues)
    if payload.available_ingredients:
        fields.add("available_ingredients")
    if payload.ingredient_mode == "existing":
        fields.add("ingredient_mode")
    if strict and structured_inventory and intent.available_ingredients and (
        set(structured_inventory) != set(intent.available_ingredients)
    ):
        issues.append(IntentIssue(code="conflicting_values", text="strict ingredient inventory"))

    time_basis = intent.time_basis
    text_limit = intent.cooking_time_limit
    limits = [value for value in (text_limit, payload.cooking_time_limit) if value is not None]
    if payload.cooking_time_limit is not None:
        fields.add("cooking_time_limit")
        if text_limit is None:
            time_basis = "per_meal"
    return PlanningIntent(
        original_text=intent.original_text,
        scope=scope,
        meal_type=None if scope == "full_day" else meal_type,
        available_ingredients=tuple(dict.fromkeys((*intent.available_ingredients, *structured_inventory))),
        ingredient_mode="strict" if strict else "flexible",
        cooking_time_limit=min(limits) if limits else None,
        time_basis=time_basis,
        cuisine_preference=intent.cuisine_preference,
        flavor_preference=intent.flavor_preference,
        servings=intent.servings,
        cooking_effort_preference=intent.cooking_effort_preference,
        allergy_statements=intent.allergy_statements,
        dietary_exclusions=intent.dietary_exclusions,
        explicit_fields=frozenset(fields),
        unresolved=tuple(issues),
    )


def _localized(value: LocalizedText, language: str) -> str:
    return value.zh_cn if language == "zh-CN" else value.en_us


def _select_candidate(
    result: PlanningSuccess, settings: Settings, language: str, intent: PlanningIntent,
) -> tuple[ComposedPlan, SelectionReason]:
    if not settings.catalog_personalization or not result.alternatives:
        return result.plan, "catalog_match"

    candidates = {
        f"candidate_{index}": plan
        for index, plan in enumerate((result.plan, *result.alternatives), start=1)
    }
    contents = {
        "language": language,
        "cuisine_preference": intent.cuisine_preference,
        "candidates": [
            {
                "id": candidate_id,
                "distinct_methods": plan.diversity.distinct_methods,
                "meals": [
                    {
                        "type": meal.meal_type,
                        "estimated_minutes": meal.estimated_total_minutes,
                        "recipes": [
                            {"name": _localized(recipe.names, language), "cuisine": recipe.cuisine}
                            for recipe in meal.recipes
                        ],
                    }
                    for meal in plan.meals
                ],
            }
            for candidate_id, plan in candidates.items()
        ],
    }
    selection = generate_structured(
        settings,
        contents=json.dumps(contents, ensure_ascii=False),
        instructions=(
            "Choose one supplied candidate ID, preferring the stated cuisine where possible. "
            "Return only candidate_id and reason. "
            "Use catalog_match by default, or varied_methods if the candidate has at least two distinct methods."
        ),
        response_model=CandidateSelection,
        max_output_tokens=256,
    )
    plan = candidates.get(selection.candidate_id)
    if plan is None or (selection.reason == "varied_methods" and plan.diversity.distinct_methods < 2):
        raise PlannerFailure
    # Membership reuses the exact plan that passed all hard filters and composition checks.
    return plan, selection.reason


def _build_response(
    plan: ComposedPlan, intent: PlanningIntent, catalog: RecipeCatalog,
    language: str, mode: CatalogMode, reason: SelectionReason, unapplied: tuple[str, ...],
) -> MealPlanResponse:
    chinese = language == "zh-CN"
    names = {item.ingredient_id: _localized(item.names, language) for item in catalog.ingredients}
    available = {(item.ingredient_id, item.state) for item in intent.available_ingredients}
    additional = {}
    meals = []
    for meal in plan.meals:
        dishes = []
        for recipe in meal.recipes:
            ingredients = []
            for item in recipe.ingredients:
                name = names[item.ingredient_id]
                ingredients.append(Ingredient(name=name, quantity=item.quantity, unit=item.unit))
                if (item.ingredient_id, item.state) not in available:
                    additional[item.ingredient_id] = name

            instructions = list(recipe.steps.zh_cn if chinese else recipe.steps.en_us)
            if recipe.times.starting_assumptions:
                instructions.insert(0, _localized(recipe.times.starting_assumptions, language))
            if water := recipe.process_water:
                if ("ingredient_water", "ready_to_use") not in available:
                    additional["ingredient_water"] = names.get("ingredient_water", "水" if chinese else "Water")
                if water.quantity_ml is not None:
                    instructions.insert(0, (
                        f"另备 {water.quantity_ml:g} 毫升工序用水。"
                        if chinese else f"Set aside {water.quantity_ml:g} mL of separate process water."
                    ))
                else:
                    instructions.insert(0, "另备工序用水，用量待核实。" if chinese else (
                        "Use separate process water. The amount is unverified."
                    ))
            dishes.append(Dish(
                name=_localized(recipe.names, language), ingredients=ingredients, instructions=instructions,
            ))
        meals.append(PlannedMeal(
            meal_type=meal.meal_type, dishes=dishes,
            estimated_preparation_minutes=meal.estimated_total_minutes,
        ))

    if intent.ingredient_mode == "strict" and additional:
        raise PlannerFailure
    title = meals[0].dishes[0].name if len(meals) == len(meals[0].dishes) == 1 else (
        "目录餐单" if chinese else "Catalog meal plan"
    )
    explanation = "按目录和可校验的限制筛选。" if chinese else "Selected from the catalog using validated constraints."
    if reason == "varied_methods":
        explanation += "方案包含多种烹饪方式。" if chinese else " The plan uses several cooking methods."
    if unapplied:
        explanation += "部分偏好尚无法应用。" if chinese else " Some preferences could not be applied."
    if intent.cooking_effort_preference == "low":
        if all(score_cooking_effort((meal,)).meets_simple_meal_target for meal in plan.meals):
            explanation += (
                "已按目录估算优先选择做起来更省事的搭配。"
                if chinese else " Ranked for easier preparation using catalog estimates."
            )
        else:
            explanation += (
                "已优先考虑省事，但现有目录只能部分满足这一偏好。"
                if chinese else " Ranked for easier preparation, but the catalog could only partly meet this preference."
            )
    if mode == "development_drafts":
        explanation += "本地开发草稿，份量和耗时待核实。" if chinese else " Local draft. Portions and times are unverified."
    return MealPlanResponse(
        title=title, meals=meals, explanation=explanation, additional_ingredients=list(additional.values()),
    )


def generate_catalog_plan(
    payload: MealPlanRequest, settings: Settings, catalog: RecipeCatalog, *,
    infer_scope: bool = False, mode: CatalogMode = "production",
) -> MealPlanResponse | PlanningBlocked | NoFeasiblePlan:
    # Keep the service boundary safe for internal callers as well as the route.
    if mode == "development_drafts" and not (settings.environment == "development" and settings.catalog_use_drafts):
        raise PlannerFailure
    intent = merge_planning_request(payload, infer_scope=infer_scope)
    result = plan_from_intent(
        catalog, intent, mode=mode, candidate_limit=3 if settings.catalog_personalization else 1,
    )
    if not isinstance(result, PlanningSuccess):
        return result
    plan, reason = _select_candidate(result, settings, payload.language, intent)
    try:
        return _build_response(plan, intent, catalog, payload.language, mode, reason, result.unapplied_preferences)
    except ValidationError:
        raise PlannerFailure from None
