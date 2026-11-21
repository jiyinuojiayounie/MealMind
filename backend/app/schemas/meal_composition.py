from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.meal_plans import MealType
from app.schemas.recipe_catalog import CatalogRecord, DishRole, IngredientId, RecipeId, State, Tag, Text


class AvailableIngredient(CatalogRecord):
    ingredient_id: IngredientId
    state: State


class MealSlot(CatalogRecord):
    meal_type: MealType
    style: Literal["single_dish", "complete_meal"] = "complete_meal"
    required_roles: frozenset[DishRole] | None = None
    anchor_recipe_id: RecipeId | None = None


class CompositionRequest(CatalogRecord):
    slots: Annotated[tuple[MealSlot, ...], Field(min_length=1, max_length=4)]
    available_ingredients: tuple[AvailableIngredient, ...] = ()
    strict_ingredients: bool = False
    process_water_available: bool | None = None
    max_total_minutes_per_meal: Annotated[int, Field(gt=0)] | None = None
    excluded_ingredient_ids: frozenset[IngredientId] = frozenset()
    excluded_allergens: frozenset[Tag] = frozenset()
    require_non_spicy: bool = False
    required_dietary_tags: frozenset[Tag] = frozenset()
    unresolved_constraints: tuple[Text, ...] = ()
    prefer_low_effort: bool = False

    @model_validator(mode="after")
    def validate_slots(self):
        meal_types = {slot.meal_type for slot in self.slots}
        if len(self.slots) > 1 and (
            len(meal_types) != len(self.slots) or not {"breakfast", "lunch", "dinner"} <= meal_types
        ):
            raise ValueError("a full day requires one breakfast, lunch, and dinner, with optional snack")
        return self
