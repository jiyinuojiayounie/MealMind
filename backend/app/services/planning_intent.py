import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from app.schemas.meal_composition import AvailableIngredient, CompositionRequest, MealSlot
from app.schemas.meal_plans import MealType
from app.schemas.planning_intent import ConfirmedSafetyConstraints, IntentField, IntentIssue, PlanningIntent
from app.schemas.recipe_catalog import RecipeCatalog
from app.services.meal_composition import CatalogMode, ComposedPlan, NoFeasiblePlan, compose_candidates

FULL_DAY = {
    "安排今天三餐", "今天三餐", "安排今天的早午晚餐", "安排三餐", "安排早餐、午餐和晚餐",
    "plan a full day", "plan breakfast, lunch and dinner",
}
SINGLE_DISH = {"只做一道菜", "一道菜", "one dish", "just one dish", "make only one dish"}
COMPLETE_DINNER = {"完整晚餐", "一顿完整的晚餐", "complete dinner", "plan a complete dinner"}
SINGLE_DINNER_DISH = {"今晚只做一道菜", "晚餐只做一道菜", "one dish for dinner", "just one dish for dinner"}
MEAL_CLAUSES: dict[str, MealType] = {
    "今晚吃什么": "dinner", "晚餐": "dinner", "安排晚餐": "dinner", "plan dinner": "dinner",
    "what's for dinner": "dinner", "dinner": "dinner", "今晚": "dinner",
    "早餐": "breakfast", "安排早餐": "breakfast", "plan breakfast": "breakfast", "breakfast": "breakfast",
    "午餐": "lunch", "安排午餐": "lunch", "plan lunch": "lunch", "lunch": "lunch",
    "加餐": "snack", "安排加餐": "snack", "plan a snack": "snack", "snack": "snack",
}
MEAL_REQUEST_CLAUSES = FULL_DAY | SINGLE_DISH | SINGLE_DINNER_DISH | COMPLETE_DINNER | MEAL_CLAUSES.keys()
TIME = re.compile(
    r"(?P<per_zh>每餐\s*)?(?P<zh>[0-9]{1,3})\s*分钟(?:以内|内)"
    r"|(?P<per_en>each meal\s+)?within\s+(?P<en>[0-9]{1,3})\s+minutes?"
    r"(?P<per_end>\s+(?:per meal|each))?"
)
INVENTORY = re.compile(
    r"(?P<strict>我只有|只有|只用|i only have\s+|i have only\s+|only use\s+)"
    r"(?P<restricted>.+)|(?:我有|i have\s+)(?P<available>.+)"
)
ALLERGY = re.compile(r"过敏|过敏反应|allerg\w*|anaphyla\w*|intoleran\w*|不耐受")
DIETARY = re.compile(
    r"不能吃|不吃|忌口|忌食|不含|禁食|素食|清真|无麸质|不放|不要|不加"
    r"|\b(?:no|without|avoid|exclude|free[ -]from|vegan|vegetarian|halal|kosher|celiac|gluten[ -]free|cannot eat|can't eat|must not)\b"
)
INGREDIENT_ALIASES = {
    "鸡蛋": ("ingredient_egg", "raw"), "eggs": ("ingredient_egg", "raw"), "egg": ("ingredient_egg", "raw"),
    "番茄": ("ingredient_tomato", "raw"), "西红柿": ("ingredient_tomato", "raw"),
    "tomato": ("ingredient_tomato", "raw"), "tomatoes": ("ingredient_tomato", "raw"),
    "熟米饭": ("ingredient_rice", "cooked"), "cooked rice": ("ingredient_rice", "cooked"),
    "大米": ("ingredient_rice", "dry"), "dry rice": ("ingredient_rice", "dry"),
    "北豆腐": ("ingredient_tofu", "ready_to_use"), "firm tofu": ("ingredient_tofu", "ready_to_use"),
    "小白菜": ("ingredient_bok_choy", "raw"), "bok choy": ("ingredient_bok_choy", "raw"),
    "水": ("ingredient_water", "ready_to_use"), "water": ("ingredient_water", "ready_to_use"),
    "盐": ("ingredient_salt", "ready_to_use"), "salt": ("ingredient_salt", "ready_to_use"),
    "葱": ("ingredient_scallion", "raw"), "scallion": ("ingredient_scallion", "raw"),
    "食用油": ("ingredient_oil", "ready_to_use"), "cooking oil": ("ingredient_oil", "ready_to_use"),
    "蒜": ("ingredient_garlic", "raw"), "garlic": ("ingredient_garlic", "raw"),
}
# Split explicit clauses, but preserve closed inventory lists with “and” or “、”.
CLAUSE_SEPARATOR = re.compile(r"[。!?;\n,]+|(?<=\D)\.\s+")


def resolve_inventory_labels(labels: list[str], issues: list[IntentIssue]) -> tuple[AvailableIngredient, ...]:
    items = []
    for label in labels:
        normalized = unicodedata.normalize("NFKC", label).casefold().strip()
        mapping = INGREDIENT_ALIASES.get(normalized)
        if mapping is None:
            issues.append(IntentIssue(code="unknown_ingredient", text=label.strip()))
        else:
            ingredient_id, state = mapping
            items.append(AvailableIngredient(ingredient_id=ingredient_id, state=state))
    return tuple(dict.fromkeys(items))


def extract_planning_intent(text: str) -> PlanningIntent:
    if len(text) > 2000:
        return PlanningIntent(original_text=text, unresolved=(IntentIssue(code="request_too_long", text=""),))
    normalized = unicodedata.normalize("NFKC", text).casefold()
    protected_full_day = "plan breakfast, lunch and dinner"
    normalized = normalized.replace(protected_full_day, "plan a full day")
    normalized = normalized.replace("’", "'").replace("！", "!").replace("？", "?")
    clauses = tuple(part.strip(" .\t\r") for part in CLAUSE_SEPARATOR.split(normalized) if part.strip(" .\t\r"))
    issues: list[IntentIssue] = []
    fields: set[IntentField] = set()
    scopes = set()
    meal_types: set[MealType] = set()
    times: set[tuple[int, bool]] = set()
    inventory: list[tuple[bool, tuple[AvailableIngredient, ...]]] = []
    allergies = []
    dietary = []
    cuisine = None
    flavors = set()

    for clause in clauses:
        for prefix in ("请帮我", "帮我"):
            if clause.startswith(prefix) and (request := clause.removeprefix(prefix).strip()) in MEAL_REQUEST_CLAUSES:
                clause = request
                break

        if clause in FULL_DAY:
            scopes.add("full_day")
        elif clause in SINGLE_DISH or clause in SINGLE_DINNER_DISH:
            scopes.add("single_dish")
            if clause in SINGLE_DINNER_DISH:
                meal_types.add("dinner")
        elif clause in COMPLETE_DINNER:
            scopes.add("complete_meal")
            meal_types.add("dinner")
        elif clause in MEAL_CLAUSES:
            meal_types.add(MEAL_CLAUSES[clause])
        elif clause == "适合一个人做":
            fields.update(("servings", "cooking_effort"))
        elif clause == "简单省事":
            fields.add("cooking_effort")
        elif clause in {"不要辣", "not spicy", "no spice", "non-spicy"}:
            flavors.add("no_spicy")
        elif clause in {"微辣", "mildly spicy"}:
            flavors.add("mild")
        elif clause in {"中餐", "中式家常菜", "chinese home cooking", "chinese food"}:
            cuisine = "chinese_home_cooking"
        elif ALLERGY.search(clause):
            allergies.append(clause)
        elif DIETARY.search(clause):
            dietary.append(clause)
        elif match := TIME.fullmatch(clause):
            minutes = int(match["zh"] or match["en"])
            if 1 <= minutes <= 480:
                times.add((minutes, bool(match["per_zh"] or match["per_en"] or match["per_end"])))
            else:
                issues.append(IntentIssue(code="unrecognized_clause", text=clause))
        elif clause.startswith(("whole day within ", "全天总共")):
            issues.append(IntentIssue(code="unsupported_time_scope", text=clause))
        elif match := INVENTORY.fullmatch(clause):
            labels = re.split(r"\s*(?:、|和|与)\s*|\s+and\s+", match["restricted"] or match["available"])
            inventory.append((bool(match["strict"]), resolve_inventory_labels(labels, issues)))
        else:
            issues.append(IntentIssue(code="unrecognized_clause", text=clause))

    if not clauses:
        issues.append(IntentIssue(code="missing_request", text=""))
    if scopes:
        fields.add("scope")
    if meal_types:
        fields.add("meal_type")
    if times:
        fields.add("cooking_time_limit")
    if inventory:
        fields.add("available_ingredients")
    if any(strict for strict, _ in inventory):
        fields.add("ingredient_mode")
    if cuisine:
        fields.add("cuisine")
    if flavors:
        fields.add("flavor")
    if allergies:
        fields.add("allergies")
    if dietary:
        fields.add("dietary_exclusions")

    for name, values in (
        ("scope", scopes), ("meal_type", meal_types), ("cooking_time_limit", times), ("flavor", flavors)
    ):
        if len(values) > 1:
            issues.append(IntentIssue(code="conflicting_values", text=name))
    if len(inventory) > 1:
        issues.append(IntentIssue(code="conflicting_values", text="available_ingredients"))

    scope = next(iter(scopes)) if len(scopes) == 1 else "complete_meal"
    meal_type = next(iter(meal_types)) if len(meal_types) == 1 else "dinner"
    if scope == "full_day" and meal_types:
        issues.append(IntentIssue(code="conflicting_values", text="full_day and individual meal type"))
    minutes, per_meal = next(iter(times)) if len(times) == 1 else (None, False)
    if scope == "full_day" and minutes is not None and not per_meal:
        issues.append(IntentIssue(code="ambiguous_time_scope", text="full_day cooking time limit"))
    strict, available = inventory[0] if len(inventory) == 1 else (False, ())
    return PlanningIntent(
        original_text=text,
        scope=scope,
        meal_type=None if scope == "full_day" else meal_type,
        available_ingredients=available,
        ingredient_mode="strict" if strict else "flexible",
        cooking_time_limit=minutes,
        time_basis="per_meal" if per_meal else "unspecified",
        cuisine_preference=cuisine,
        flavor_preference=next(iter(flavors)) if len(flavors) == 1 else None,
        servings=1 if "servings" in fields else None,
        cooking_effort_preference="low" if "cooking_effort" in fields else None,
        allergy_statements=tuple(allergies),
        dietary_exclusions=tuple(dietary),
        explicit_fields=frozenset(fields),
        unresolved=tuple(issues),
    )


@dataclass(frozen=True)
class PlanningBlocked:
    status: Literal["clarification_required", "unsupported_constraints"]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PlanningSuccess:
    plan: ComposedPlan
    unapplied_preferences: tuple[str, ...] = ()
    alternatives: tuple[ComposedPlan, ...] = ()
    status: Literal["success"] = field(default="success", init=False)


def plan_from_intent(
    catalog: RecipeCatalog, intent: PlanningIntent, *, mode: CatalogMode = "production",
    candidate_limit: int = 1,
) -> PlanningSuccess | PlanningBlocked | NoFeasiblePlan:
    safety = intent.confirmed_safety or ConfirmedSafetyConstraints()
    unconfirmed = []
    if intent.allergy_statements and (
        not safety.excluded_allergens or not safety.confirmed_statements.issuperset(intent.allergy_statements)
    ):
        unconfirmed.append("unconfirmed_allergies")
    if intent.dietary_exclusions and (
        not (safety.excluded_ingredient_ids or safety.required_dietary_tags)
        or not safety.confirmed_statements.issuperset(intent.dietary_exclusions)
    ):
        unconfirmed.append("unconfirmed_dietary_exclusions")
    unknown = [issue.code for issue in intent.unresolved if issue.code != "unsupported_time_scope"]
    if intent.scope == "full_day" and intent.cooking_time_limit is not None and intent.time_basis != "per_meal":
        unknown.append("ambiguous_time_scope")
    if intent.scope == "full_day" and intent.meal_type is not None:
        unknown.append("conflicting_values")
    if intent.scope != "full_day" and intent.meal_type is None:
        unknown.append("missing_meal_type")
    if intent.ingredient_mode == "strict" and not intent.available_ingredients:
        unknown.append("missing_strict_ingredients")
    if unconfirmed or unknown:
        return PlanningBlocked("clarification_required", tuple(dict.fromkeys(unconfirmed + unknown)))

    unsupported = [issue.code for issue in intent.unresolved if issue.code == "unsupported_time_scope"]
    require_non_spicy = intent.flavor_preference == "no_spicy"
    review_status = "draft" if mode == "development_drafts" else "reviewed"
    if require_non_spicy and not any(
        recipe.review.status == review_status and recipe.flavor and recipe.flavor.has_verified_heat
        for recipe in catalog.recipes
    ):
        unsupported.append("unverified_flavor_constraint")
    if unsupported:
        return PlanningBlocked("unsupported_constraints", tuple(unsupported))

    if intent.scope == "full_day":
        slots = tuple(MealSlot(meal_type=kind) for kind in ("breakfast", "lunch", "dinner"))
    else:
        slots = (MealSlot(meal_type=intent.meal_type, style=intent.scope),)
    request = CompositionRequest(
        slots=slots,
        available_ingredients=intent.available_ingredients,
        strict_ingredients=intent.ingredient_mode == "strict",
        process_water_available=True if any(
            item.ingredient_id == "ingredient_water" and item.state == "ready_to_use"
            for item in intent.available_ingredients
        ) else None,
        max_total_minutes_per_meal=intent.cooking_time_limit,
        require_non_spicy=require_non_spicy,
        excluded_ingredient_ids=safety.excluded_ingredient_ids,
        excluded_allergens=safety.excluded_allergens,
        required_dietary_tags=safety.required_dietary_tags,
        prefer_low_effort=intent.cooking_effort_preference == "low",
    )
    if intent.servings is not None:
        recipes = tuple(recipe for recipe in catalog.recipes if recipe.servings == intent.servings)
        catalog = catalog.model_copy(update={"recipes": recipes})

    unapplied = ("flavor_preference",) if intent.flavor_preference == "mild" else ()
    if request.prefer_low_effort:
        # Keep the deterministic effort winner rather than handing the ranking to personalization.
        candidate_limit = 1
    if intent.cuisine_preference:
        preferred = tuple(recipe for recipe in catalog.recipes if recipe.cuisine == intent.cuisine_preference)
        if preferred:
            result = compose_candidates(
                catalog.model_copy(update={"recipes": preferred}), request, mode=mode, limit=candidate_limit
            )
            if isinstance(result, tuple):
                return PlanningSuccess(result[0], unapplied, result[1:])
        unapplied += ("cuisine_preference",)
    result = compose_candidates(catalog, request, mode=mode, limit=candidate_limit)
    if isinstance(result, tuple):
        return PlanningSuccess(result[0], unapplied, result[1:])
    if result.reason == "unresolved_constraints":
        return PlanningBlocked("clarification_required", ("unresolved_canonical_constraints",))
    return result
