from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.nutrition_reference import ReferenceRecord

NutritionReason = Literal[
    "food_not_found", "ambiguous_food_match", "food_state_unknown", "food_preparation_mismatch",
    "mixed_dish_unsupported", "quantity_unknown", "invalid_quantity", "portion_needs_review",
    "food_reference_binding_invalid", "food_reference_binding_stale", "food_reference_binding_version_unavailable",
    "unsupported_unit", "unsupported_serving_conversion", "nutrient_data_missing",
]
Estimate = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
CalculationVersion = Literal["nutrition-v1"]


class NutrientEstimates(ReferenceRecord):
    energy_kcal: Estimate | None = None
    protein_g: Estimate | None = None
    carbohydrate_g: Estimate | None = None
    fat_g: Estimate | None = None


class NutritionProvenance(ReferenceRecord):
    food_id: str
    fdc_id: int
    reference_version: str
    source_release: str
    source_url: str
    state: Literal["raw", "cooked", "dry", "as_sold"]
    nutrient_source_row_ids: dict[str, int]
    portion_source_row_id: int | None = None


class ItemNutritionResult(ReferenceRecord):
    name: str
    calculation_version: CalculationVersion = "nutrition-v1"
    status: Literal["calculated", "partial", "not_calculable"]
    nutrients: NutrientEstimates = NutrientEstimates()
    edible_grams: Decimal | None = None
    conversion: Literal["edible_mass", "reference_portion"] | None = None
    provenance: NutritionProvenance | None = None
    reasons: tuple[NutritionReason, ...] = ()
    limitations: tuple[str, ...] = ()


class NutrientSubtotal(ReferenceRecord):
    unit: Literal["kcal", "g"]
    subtotal: Decimal | None
    contributing_items: int
    missing_items: int


class NutritionSubtotals(ReferenceRecord):
    energy_kcal: NutrientSubtotal
    protein_g: NutrientSubtotal
    carbohydrate_g: NutrientSubtotal
    fat_g: NutrientSubtotal


class NutritionAggregate(ReferenceRecord):
    status: Literal["no_items", "not_calculable", "partial", "all_logged_items_calculated"]
    calculation_version: CalculationVersion = "nutrition-v1"
    day_completeness: Literal["not_assessed"] = "not_assessed"
    item_count: int
    calculated_item_count: int
    fully_calculated_item_count: int
    uncalculated_item_count: int
    nutrients: NutritionSubtotals
