import hashlib
import json
import re
from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.settings import Settings
from app.schemas.food_logs import FoodLog
from app.schemas.meal_plans import MealPlanRequest, MealPlanResponse, MealType, ingredient_key
from app.schemas.recipe_catalog import RecipeCatalog
from app.schemas.replan import ReplanContext, ReplanPreview, ReplanRequest
from app.services.catalog_planning import generate_catalog_plan, merge_planning_request
from app.services.meal_composition import NoFeasiblePlan
from app.services.meal_plans import PlannerFailure, generate_meal_plan
from app.services.planning_intent import PlanningBlocked
from app.services.recipe_catalog import DEVELOPMENT_CATALOG_PATH, CatalogLoadError, load_recipe_catalog
from app.storage.food_logs import FoodLogStore

MAIN_MEALS: tuple[MealType, ...] = ("breakfast", "lunch", "dinner")
MEAL_ORDER: tuple[MealType, ...] = (*MAIN_MEALS, "snack")
COMPENSATION = re.compile(
    r"跳过.{0,5}[早午晚]?餐|不吃[早午晚]餐|节食|卡路里赤字|热量赤字|补偿.{0,8}(摄入|热量)"
    r"|\bskip (?:a |the |your )?(?:meal|breakfast|lunch|dinner)\b"
    r"|\b(?:calorie deficit|compensate for|make up for (?:earlier|lunch|breakfast))\b",
    re.IGNORECASE,
)
NUTRITION_CLAIM = re.compile(r"\d\s*(?:kcal\b|calories\b|千卡|大卡|卡路里)", re.IGNORECASE)


class ReplanBlocked(Exception):
    def __init__(self, code: int, status: str, *reasons: str):
        self.code = code
        self.detail = {"status": status, "reasons": list(reasons)}


def local_today(timezone: str) -> date:
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ReplanBlocked(422, "invalid_timezone") from None
    return datetime.now(zone).date()


def replan_context(date: date, logs: list[FoodLog]) -> ReplanContext:
    counts = {slot: sum(log.meal_type == slot for log in logs) for slot in MEAL_ORDER}
    locked = tuple(slot for slot in MEAL_ORDER if counts[slot])
    latest = max((MAIN_MEALS.index(slot) for slot in MAIN_MEALS if counts[slot]), default=-1)
    fingerprint = hashlib.sha256(json.dumps([
        date.isoformat(), sorted((str(log.id), log.revision) for log in logs),
    ], separators=(",", ":")).encode()).hexdigest()
    return ReplanContext(
        date=date, context_fingerprint=fingerprint, confirmed_log_count=len(logs),
        confirmed_by_meal_type=counts, unspecified_log_count=sum(log.meal_type == "unspecified" for log in logs),
        locked_meal_types=locked, remaining_main_meal_types=MAIN_MEALS[latest + 1:],
    )


def _read_preview_context(
    request: ReplanRequest, store: FoodLogStore, *, after_generation: bool = False,
) -> tuple[ReplanContext, list[FoodLog]]:
    if request.date != local_today(request.timezone):
        raise ReplanBlocked(409, "stale_context" if after_generation else "date_not_today")
    logs = store.list_confirmed_by_date(request.date)
    context = replan_context(request.date, logs)
    if after_generation and request.expected_context_fingerprint != context.context_fingerprint:
        raise ReplanBlocked(409, "stale_context")
    if request.target_meal_type in context.locked_meal_types:
        raise ReplanBlocked(409, "meal_slot_completed")
    if request.target_meal_type != "snack" and request.target_meal_type not in context.remaining_main_meal_types:
        raise ReplanBlocked(409, "meal_slot_not_remaining")
    if request.expected_context_fingerprint != context.context_fingerprint:
        raise ReplanBlocked(409, "stale_context")
    return context, logs


def _planning_request(request: ReplanRequest) -> MealPlanRequest:
    constraints = request.constraints
    if constraints.restriction_status == "unreviewed":
        raise ReplanBlocked(422, "clarification_required", "review_dietary_restrictions")
    if constraints.restriction_status == "present":
        raise ReplanBlocked(422, "unsupported_constraints", "dietary_restrictions_unverified")
    if constraints.ingredient_mode == "existing" and not constraints.available_ingredients:
        raise ReplanBlocked(422, "clarification_required", "review_available_ingredients")
    clauses = [request.target_meal_type]
    if constraints.one_person:
        clauses.append("适合一个人做")
    if constraints.prefer_low_effort:
        clauses.append("简单省事")
    if request.instructions:
        clauses.append(request.instructions)
    return MealPlanRequest(
        scope="single_meal", meal_type=request.target_meal_type, user_request="; ".join(clauses),
        language=constraints.language, ingredient_mode=constraints.ingredient_mode,
        cooking_time_limit=constraints.cooking_time_limit, available_ingredients=constraints.available_ingredients,
    )


def _earlier_variety(
    catalog: RecipeCatalog, logs: list[FoodLog], target: MealType, *, chinese: bool,
) -> tuple[tuple[str, ...], frozenset[str]]:
    earlier = {slot for slot in MEAL_ORDER if MEAL_ORDER.index(slot) < MEAL_ORDER.index(target)}
    names = {ingredient_key(item.name) for log in logs if log.meal_type in earlier for item in log.items}
    recipes = tuple(recipe for recipe in catalog.recipes if names.intersection(
        (ingredient_key(recipe.names.en_us), ingredient_key(recipe.names.zh_cn)),
    ))
    ingredients = tuple(item for item in catalog.ingredients if names.intersection(
        (ingredient_key(item.names.en_us), ingredient_key(item.names.zh_cn)),
    ))
    labels = sorted({item.names.zh_cn if chinese else item.names.en_us for item in (*recipes, *ingredients)})
    return tuple(labels[:12]), frozenset(recipe.dish_family_id for recipe in recipes)


def generate_replan_preview(request: ReplanRequest, store: FoodLogStore, settings: Settings) -> ReplanPreview:
    context, logs = _read_preview_context(request, store)
    payload = _planning_request(request)
    mode = request.planning_mode or (
        "catalog" if request.current_plan and request.current_plan.source == "catalog" else "prompt_only"
    )
    intent_payload = payload if mode == "catalog" else payload.model_copy(update={"available_ingredients": []})
    intent = merge_planning_request(intent_payload, infer_scope=False)
    if intent.allergy_statements or intent.dietary_exclusions:
        raise ReplanBlocked(422, "unsupported_constraints", "dietary_restrictions_unverified")
    # Prompt-only does not independently validate spicy or textual inventory constraints.
    if mode == "prompt_only":
        if intent.flavor_preference == "no_spicy":
            raise ReplanBlocked(422, "unsupported_constraints", "flavor_constraint_unverified")
        if "available_ingredients" in intent.explicit_fields:
            raise ReplanBlocked(422, "clarification_required", "confirm_ingredients_as_structured_fields")
        payload = payload.model_copy(update={"cooking_time_limit": intent.cooking_time_limit})
    if intent.unresolved:
        raise ReplanBlocked(422, "clarification_required", *dict.fromkeys(issue.code for issue in intent.unresolved))
    if intent.scope == "full_day":
        raise ReplanBlocked(422, "clarification_required", "one_target_meal_required")

    if mode == "catalog" and not settings.catalog_planning_enabled:
        raise ReplanBlocked(403, "catalog_disabled")
    labels: tuple[str, ...] = ()
    families: frozenset[str] = frozenset()
    previous_meals = request.current_plan.plan.meals if request.current_plan else ()
    recent_dishes = tuple(dict.fromkeys(dish.name for meal in previous_meals for dish in meal.dishes))[:16]
    catalog = None
    if mode == "catalog" or logs:
        try:
            catalog = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)
        except CatalogLoadError:
            if mode == "catalog":
                raise
        if catalog:
            labels, families = _earlier_variety(catalog, logs, request.target_meal_type, chinese=payload.language == "zh-CN")

    if mode == "catalog":
        if catalog is None:
            raise CatalogLoadError("Catalog is unavailable for replanning")
        recent = {ingredient_key(name) for name in recent_dishes}
        families |= frozenset(
            recipe.dish_family_id for recipe in catalog.recipes
            if recent.intersection((ingredient_key(recipe.names.zh_cn), ingredient_key(recipe.names.en_us)))
        )
        plan = generate_catalog_plan(
            payload, settings.model_copy(update={"catalog_personalization": False}), catalog,
            mode="development_drafts" if settings.catalog_use_drafts else "production", recent_family_ids=families,
        )
        if isinstance(plan, PlanningBlocked):
            raise ReplanBlocked(422, plan.status, *plan.reasons)
        if isinstance(plan, NoFeasiblePlan):
            raise ReplanBlocked(409, plan.status, plan.reason)
    else:
        plan = generate_meal_plan(
            payload, settings, replan_food_names=labels, replan_recent_dishes=recent_dishes,
        )
    _check_suggestion(plan, request.target_meal_type)
    _read_preview_context(request, store, after_generation=True)

    previous = request.current_plan
    meals = previous.plan.meals if previous else ()
    return ReplanPreview(
        proposal_id=uuid4(), date=request.date, timezone=request.timezone, target_meal_type=request.target_meal_type,
        source=mode, current_meal=next((meal for meal in meals if meal.meal_type == request.target_meal_type), None),
        suggested_plan=plan, untouched_meal_types=tuple(meal.meal_type for meal in meals if meal.meal_type != request.target_meal_type),
        base_plan_id=previous.plan_id if previous else None, base_plan_revision=previous.revision if previous else None,
        context=context, context_fingerprint=context.context_fingerprint, variety_match_count=len(labels),
        uncertainty=("day_intake_incomplete_or_unknown", "nutrition_coverage_not_used"),
    )


def _check_suggestion(plan: MealPlanResponse, target: MealType) -> None:
    if [meal.meal_type for meal in plan.meals] != [target]:
        raise PlannerFailure
    texts = [plan.title, plan.explanation, *plan.additional_ingredients]
    for dish in plan.meals[0].dishes:
        texts.extend([dish.name, *dish.instructions, *(ingredient.name for ingredient in dish.ingredients)])
    if any(COMPENSATION.search(text) or NUTRITION_CLAIM.search(text) for text in texts):
        raise PlannerFailure
