from typing import Annotated, Literal

from pydantic import Field

from app.schemas.meal_composition import AvailableIngredient
from app.schemas.meal_plans import MealType
from app.schemas.recipe_catalog import CatalogRecord, IngredientId, Tag

IntentField = Literal[
    "scope", "meal_type", "available_ingredients", "ingredient_mode", "cooking_time_limit",
    "cuisine", "flavor", "servings", "vegetarian_preference", "cooking_effort", "allergies", "dietary_exclusions",
]


class IntentIssue(CatalogRecord):
    code: Literal[
        "unrecognized_clause", "unknown_ingredient", "conflicting_values",
        "ambiguous_time_scope", "missing_request", "request_too_long", "unsupported_time_scope",
    ]
    text: str


class ConfirmedSafetyConstraints(CatalogRecord):
    """Canonical constraints supplied by a trusted confirmation step outside extraction."""

    confirmed_statements: frozenset[str] = frozenset()
    excluded_allergens: frozenset[Tag] = frozenset()
    excluded_ingredient_ids: frozenset[IngredientId] = frozenset()
    required_dietary_tags: frozenset[Tag] = frozenset()


class PlanningIntent(CatalogRecord):
    original_text: str
    scope: Literal["single_dish", "complete_meal", "full_day"] = "complete_meal"
    meal_type: MealType | None = "dinner"
    available_ingredients: tuple[AvailableIngredient, ...] = ()
    ingredient_mode: Literal["strict", "flexible"] = "flexible"
    cooking_time_limit: Annotated[int, Field(ge=1, le=480)] | None = None
    time_basis: Literal["per_meal", "unspecified"] = "unspecified"
    cuisine_preference: Tag | None = None
    flavor_preference: Literal["no_spicy", "mild"] | None = None
    servings: Literal[1] | None = None
    vegetarian_preference: bool = False
    cooking_effort_preference: Literal["low"] | None = None
    allergy_statements: tuple[str, ...] = ()
    dietary_exclusions: tuple[str, ...] = ()
    confirmed_safety: ConfirmedSafetyConstraints | None = None
    explicit_fields: frozenset[IntentField] = frozenset()
    unresolved: tuple[IntentIssue, ...] = ()
