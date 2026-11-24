from collections.abc import Collection
from dataclasses import dataclass, field
from bisect import insort
from itertools import combinations, product
from typing import Literal

from app.schemas.meal_composition import CompositionRequest, MealSlot
from app.schemas.meal_plans import MealType
from app.schemas.recipe_catalog import CatalogRecipe, DishRole, RecipeCatalog
from app.services.recipe_catalog import production_recipes, recipes_with_allergen_evidence

DEFAULT_ROLES: dict[MealType, frozenset[DishRole]] = {
    "breakfast": frozenset({"protein", "staple"}),
    "lunch": frozenset({"protein", "staple", "vegetable"}),
    "dinner": frozenset({"protein", "staple", "vegetable"}),
    "snack": frozenset(),
}
CatalogMode = Literal["production", "development_drafts"]


@dataclass(frozen=True)
class MealCombination:
    meal_type: MealType
    recipes: tuple[CatalogRecipe, ...]
    required_roles: frozenset[DishRole]
    covered_roles: frozenset[DishRole]
    estimated_total_minutes: int

    @property
    def composition_type(self) -> Literal["single_recipe_complete", "main_plus_staple", "multi_dish"] | None:
        if len(self.recipes) == 1:
            if self.required_roles and self.required_roles <= self.covered_roles:
                return "single_recipe_complete"
            return None
        if len(self.recipes) == 2:
            for main, staple in (self.recipes, self.recipes[::-1]):
                staple_roles = set(staple.dish_roles)
                if (
                    "staple" in staple_roles and staple_roles <= {"staple", "accompaniment"}
                    and "protein" in main.dish_roles
                ):
                    return "main_plus_staple"
        return "multi_dish"


def heated_components(recipe: CatalogRecipe) -> int:
    if recipe.cooking_components is not None:
        return recipe.cooking_components
    return int(recipe.times.cooking_minutes > 0)


@dataclass(frozen=True)
class CookingEffortScore:
    dishes: int
    total_minutes: int
    distinct_ingredients: int
    prerequisites: int
    heated_components: int
    equipment_load: int

    @property
    def points(self) -> int:
        return (
            12 * self.dishes + self.total_minutes + 3 * self.distinct_ingredients + 8 * self.prerequisites
            + 6 * self.heated_components + self.equipment_load
        )

    @property
    def meets_simple_meal_target(self) -> bool:
        return (
            self.dishes <= 2 and self.total_minutes <= 30
            and self.distinct_ingredients <= 8 and self.prerequisites == 0 and self.heated_components <= 1
        )


def score_cooking_effort(meals: Collection[MealCombination]) -> CookingEffortScore:
    dishes = tuple(recipe for meal in meals for recipe in meal.recipes)
    items = [item for recipe in dishes for item in recipe.ingredients]
    return CookingEffortScore(
        dishes=len(dishes),
        total_minutes=sum(meal.estimated_total_minutes for meal in meals),
        distinct_ingredients=len({item.ingredient_id for item in items}),
        prerequisites=len({(item.ingredient_id, item.state) for item in items if item.required_starting_state}),
        heated_components=sum(heated_components(recipe) for recipe in dishes),
        equipment_load=sum(len({*recipe.equipment} - {"knife", "cutting_board", "spoon"}) for recipe in dishes),
    )


@dataclass(frozen=True)
class DiversityScore:
    repeated_recipes: int
    repeated_families: int
    repeated_primary_ingredients: int
    distinct_methods: int
    distinct_compositions: int
    recent_family_matches: int

    @property
    def points(self) -> int:
        return (
            -100 * self.repeated_recipes - 50 * self.repeated_families
            - 4 * self.repeated_primary_ingredients - 18 * self.recent_family_matches
            + 2 * self.distinct_methods + 2 * self.distinct_compositions
        )


@dataclass(frozen=True)
class ComposedPlan:
    meals: tuple[MealCombination, ...]
    diversity: DiversityScore
    status: Literal["feasible"] = field(default="feasible", init=False)


@dataclass(frozen=True)
class NoFeasiblePlan:
    reason: Literal["unresolved_constraints", "no_slot_combination", "no_distinct_day"]
    blocked_meals: tuple[MealType, ...] = ()
    status: Literal["no_feasible_plan"] = field(default="no_feasible_plan", init=False)


def _eligible_recipes(
    catalog: RecipeCatalog, request: CompositionRequest, mode: CatalogMode
) -> tuple[CatalogRecipe, ...]:
    if mode == "development_drafts":
        drafts = (recipe for recipe in catalog.recipes if recipe.review.status == "draft")
        return recipes_with_allergen_evidence(catalog, drafts, request.excluded_allergens)
    return production_recipes(catalog, excluded_allergens=request.excluded_allergens)


def _matches_constraints(
    recipe: CatalogRecipe,
    request: CompositionRequest,
    available: set[tuple[str, str]],
) -> bool:
    vegetarian = recipe.dietary.get("vegetarian")
    if request.vegetarian_preference and (vegetarian is None or vegetarian.status == "unknown"):
        return False
    if request.require_non_spicy and not (
        recipe.flavor and recipe.flavor.has_verified_heat and recipe.flavor.heat == "non_spicy"
    ):
        return False
    if request.max_total_minutes_per_meal is not None and (
        recipe.times.total_minutes > request.max_total_minutes_per_meal
    ):
        return False
    if any(
        tag not in recipe.dietary or recipe.dietary[tag].status != "verified"
        or recipe.dietary[tag].evidence is None
        for tag in request.required_dietary_tags
    ):
        return False
    if recipe.process_water and (
        "ingredient_water" in request.excluded_ingredient_ids
        or request.process_water_available is False
        or (request.strict_ingredients and request.process_water_available is not True)
    ):
        return False

    return all(
        item.ingredient_id not in request.excluded_ingredient_ids
        and (
            not (request.strict_ingredients or item.required_starting_state)
            or (item.ingredient_id, item.state) in available
        )
        for item in recipe.ingredients
    )


def _has_unresolved_constraints(catalog: RecipeCatalog, request: CompositionRequest) -> bool:
    known_ingredients = {item.ingredient_id for item in catalog.ingredients}
    return bool(request.unresolved_constraints or request.excluded_ingredient_ids - known_ingredients)


def retrieve_candidates(
    catalog: RecipeCatalog,
    request: CompositionRequest,
    meal_type: MealType,
    *,
    roles: frozenset[DishRole] = frozenset(),
    mode: CatalogMode = "production",
) -> tuple[CatalogRecipe, ...]:
    if _has_unresolved_constraints(catalog, request):
        return ()
    available = {(item.ingredient_id, item.state) for item in request.available_ingredients}
    return tuple(sorted(
        (
            recipe for recipe in _eligible_recipes(catalog, request, mode)
            if meal_type in recipe.meal_types and roles.issubset(recipe.dish_roles)
            and _matches_constraints(recipe, request, available)
        ),
        key=lambda recipe: recipe.recipe_id,
    ))


def _meal_combinations(
    catalog: RecipeCatalog, request: CompositionRequest, slot: MealSlot, mode: CatalogMode
) -> tuple[MealCombination, ...]:
    roles = slot.required_roles
    if roles is None:
        roles = DEFAULT_ROLES[slot.meal_type] if slot.style == "complete_meal" else frozenset()

    candidates = retrieve_candidates(catalog, request, slot.meal_type, mode=mode)
    max_dishes = 1 if slot.style == "single_dish" else max(1, len(roles) + bool(slot.anchor_recipe_id))
    results = []
    for size in range(1, max_dishes + 1):
        for dishes in combinations(candidates, size):
            if slot.anchor_recipe_id and all(dish.recipe_id != slot.anchor_recipe_id for dish in dishes):
                continue
            if len({dish.dish_family_id for dish in dishes}) != size:
                continue
            total = sum(dish.times.total_minutes for dish in dishes)
            if request.max_total_minutes_per_meal is not None and total > request.max_total_minutes_per_meal:
                continue
            covered = frozenset(role for dish in dishes for role in dish.dish_roles)
            if not roles <= covered:
                continue
            if size > 1 and any(
                dish.recipe_id != slot.anchor_recipe_id
                and roles <= {role for other in dishes if other != dish for role in other.dish_roles}
                for dish in dishes
            ):
                continue
            results.append(MealCombination(slot.meal_type, dishes, roles, covered, total))
    return tuple(results)


def score_diversity(
    meals: Collection[MealCombination], *, recent_family_ids: Collection[str] = (),
) -> DiversityScore:
    dishes = tuple(dish for meal in meals for dish in meal.recipes)
    recipe_ids = {dish.recipe_id for dish in dishes}
    families = {dish.dish_family_id for dish in dishes}
    # Count ingredient presence once per meal so dishes served together do not look like repeated meals.
    primary_by_meal = [
        {item.ingredient_id for dish in meal.recipes for item in dish.ingredients if item.primary}
        for meal in meals
    ]
    return DiversityScore(
        repeated_recipes=len(dishes) - len(recipe_ids),
        repeated_families=len(dishes) - len(families),
        repeated_primary_ingredients=(
            sum(map(len, primary_by_meal)) - len(set().union(*primary_by_meal))
        ),
        distinct_methods=len({method for dish in dishes for method in dish.cooking_methods}),
        distinct_compositions=len({
            tuple(sorted(tuple(sorted(dish.dish_roles)) for dish in meal.recipes))
            for meal in meals
        }),
        recent_family_matches=len(families.intersection(recent_family_ids)),
    )


def compose_candidates(
    catalog: RecipeCatalog,
    request: CompositionRequest,
    *,
    mode: CatalogMode = "production",
    recent_family_ids: Collection[str] = (),
    limit: int = 1,
) -> tuple[ComposedPlan, ...] | NoFeasiblePlan:
    if limit < 1:
        raise ValueError("candidate limit must be positive")
    if _has_unresolved_constraints(catalog, request):
        return NoFeasiblePlan("unresolved_constraints")

    order = tuple(DEFAULT_ROLES)
    slots = sorted(request.slots, key=lambda slot: order.index(slot.meal_type))
    options = [_meal_combinations(catalog, request, slot, mode) for slot in slots]
    blocked = tuple(slot.meal_type for slot, candidates in zip(slots, options) if not candidates)
    if blocked:
        return NoFeasiblePlan("no_slot_combination", blocked)

    ranked = []
    for meals in product(*options):
        diversity = score_diversity(meals, recent_family_ids=recent_family_ids)
        if diversity.repeated_recipes or diversity.repeated_families:
            continue
        rank = (
            -diversity.points,
            sum(len(meal.recipes) for meal in meals),
            sum(meal.estimated_total_minutes for meal in meals),
            tuple(tuple(recipe.recipe_id for recipe in meal.recipes) for meal in meals),
        )
        if all(slot.style == "complete_meal" for slot in slots):
            effort = score_cooking_effort(meals)
            rank = (
                effort.points * (2 if request.prefer_low_effort else 1) - diversity.points,
                sum(meal.composition_type == "multi_dish" for meal in meals),
                *rank,
            )
        # Breakfast preference is soft. Catalog coverage and hard constraints still determine feasibility.
        breakfast = next((meal for meal in meals if meal.meal_type == "breakfast" and meal.required_roles), None)
        if breakfast:
            rank = (
                breakfast.estimated_total_minutes > 15,
                sum(heated_components(recipe) for recipe in breakfast.recipes) > 1,
                *rank,
            )
        if len(ranked) < limit or rank < ranked[-1][0]:
            insort(ranked, (rank, ComposedPlan(meals, diversity)), key=lambda item: item[0])
            if len(ranked) > limit:
                ranked.pop()

    return tuple(plan for _, plan in ranked) if ranked else NoFeasiblePlan("no_distinct_day")


def compose_plan(
    catalog: RecipeCatalog,
    request: CompositionRequest,
    *,
    mode: CatalogMode = "production",
    recent_family_ids: Collection[str] = (),
) -> ComposedPlan | NoFeasiblePlan:
    candidates = compose_candidates(catalog, request, mode=mode, recent_family_ids=recent_family_ids)
    return candidates[0] if isinstance(candidates, tuple) else candidates
