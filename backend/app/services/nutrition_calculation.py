import re
from collections.abc import Iterable
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from app.schemas.food_logs import FoodItem
from app.schemas.nutrition_calculation import (
    ItemNutritionResult, NutrientEstimates, NutrientSubtotal, NutritionAggregate, NutritionProvenance,
    NutritionReason, NutritionSubtotals,
)
from app.schemas.nutrition_reference import (
    NUTRIENT_DEFINITIONS, NutritionFood, NutritionReference, UsdaPortion, normalize_food_label,
)
from app.services.nutrition_reference import load_nutrition_reference

ARITHMETIC = Context(prec=50, rounding=ROUND_HALF_EVEN)
MAX_EDIBLE_GRAMS = Decimal("100000")

MASS_FACTORS = {
    "g": Decimal("1"), "gram": Decimal("1"), "grams": Decimal("1"), "克": Decimal("1"), "公克": Decimal("1"),
    "kg": Decimal("1000"), "kilogram": Decimal("1000"), "kilograms": Decimal("1000"),
    "千克": Decimal("1000"), "公斤": Decimal("1000"),
    "mg": Decimal("0.001"), "milligram": Decimal("0.001"), "milligrams": Decimal("0.001"), "毫克": Decimal("0.001"),
}
HOUSEHOLD_UNITS = frozenset({
    "碗", "杯", "个", "枚", "根", "块", "片", "份", "勺", "小把", "把", "汤匙", "茶匙", "ml", "毫升",
    "bowl", "bowls", "cup", "cups", "piece", "pieces", "serving", "servings", "handful", "handfuls",
    "tbsp", "tsp", "tablespoon", "teaspoon",
})

# Exact qualifiers only. Generic preparation words can't identify a raw/cooked variant
# unless the food name already provides the relevant food identity.
PREPARATIONS = {
    "raw": "raw", "生": "raw", "生的": "raw", "未烹调": "raw", "uncooked": "raw",
    "dry": "dry", "干": "dry",
    "cooked": "cooked", "熟": "cooked", "熟的": "cooked",
    "as sold": "as_sold",
    "roasted": "roasted", "roast": "roasted", "烤": "roasted",
    "stewed": "stewed", "炖": "stewed",
    "boiled": "boiled", "煮": "boiled", "水煮": "boiled",
    "hard-boiled": "hard-boiled", "全熟水煮": "hard-boiled",
    "poached": "poached", "水煮荷包": "poached",
    "baked": "baked", "烘烤": "baked",
}
STATES = frozenset({"raw", "dry", "cooked", "as_sold"})
QUALIFIED_FOODS = {
    "去皮去骨鸡胸肉": {
        "raw": "chicken_breast_skinless_boneless_raw",
        "roasted": "chicken_breast_meat_roasted",
        "stewed": "chicken_breast_meat_stewed",
    },
    "长粒糙米": {"raw": "brown_rice_long_grain_raw", "cooked": "brown_rice_long_grain_cooked"},
    "rice noodles": {"dry": "rice_noodles_dry", "cooked": "rice_noodles_cooked"},
}
QUALIFIED_FOODS["skinless boneless chicken breast"] = QUALIFIED_FOODS["去皮去骨鸡胸肉"]
UNSPECIFIED_STATE = frozenset({"鸡胸肉", "chicken breast", "鸡蛋", "egg", "eggs", "brown rice", "白米", "土豆", "红薯"})
KNOWN_MIXED_DISHES = frozenset({
    "番茄炒蛋", "西红柿炒鸡蛋", "宫保鸡丁", "蛋炒饭", "炒饭", "麻婆豆腐", "牛肉面",
    "fried rice", "egg fried rice", "kung pao chicken", "mapo tofu", "beef noodle soup",
})
PORTION_UNITS = {
    "usda large egg": {"whole_egg_raw": 88374, "whole_egg_hard_boiled": 92500},
    "美标大号鸡蛋": {"whole_egg_raw": 88374, "whole_egg_hard_boiled": 92500},
    "usda medium banana": {"banana_raw": 93515},
    "美标中等香蕉": {"banana_raw": 93515},
}


class NutritionCalculator:
    def __init__(self, reference: NutritionReference | None = None):
        self.reference = load_nutrition_reference() if reference is None else reference
        self.by_id = {food.food_id: food for food in self.reference.foods}
        self.by_label = {
            normalize_food_label(label): food
            for food in self.reference.foods for label in (food.names.zh_cn, food.names.en_us, *food.aliases)
        }
        self.unresolved_labels = {normalize_food_label(label) for label in self.reference.unresolved_labels}

    def _match(self, item: FoodItem) -> tuple[NutritionFood | None, NutritionReason | None]:
        label = normalize_food_label(item.name)
        preparation = normalize_food_label(item.preparation_method or "")
        method = PREPARATIONS.get(preparation)
        if food := self.by_label.get(label):
            if not preparation:
                return food, None
            if method in STATES and food.state == method:
                return food, None
            if method and method not in STATES and food.state == "cooked" and re.search(
                rf"\b{re.escape(method)}\b", food.preparation.casefold(),
            ):
                return food, None
            return None, "food_preparation_mismatch"

        if variants := QUALIFIED_FOODS.get(label):
            if method is None and not preparation:
                return None, "food_state_unknown"
            if method and (food := self.by_id.get(variants.get(method, ""))):
                return food, None
            compatible_state = sum(self.by_id[key].state == method for key in variants.values() if key in self.by_id)
            return None, "ambiguous_food_match" if compatible_state > 1 else "food_preparation_mismatch"
        if label in KNOWN_MIXED_DISHES:
            return None, "mixed_dish_unsupported"
        if label in UNSPECIFIED_STATE and not preparation:
            return None, "food_state_unknown"
        if label in self.unresolved_labels or label in UNSPECIFIED_STATE:
            return None, "ambiguous_food_match"
        return None, "food_not_found"

    def calculate_item(self, item: FoodItem) -> ItemNutritionResult:
        food, match_issue = self._match(item)
        quantity, quantity_issue = _quantity(item.quantity)
        reasons = tuple(issue for issue in (match_issue, quantity_issue) if issue is not None)
        if food is None:
            return ItemNutritionResult(name=item.name, status="not_calculable", reasons=reasons)

        source_rows = {
            key: value.source_row_id for key in NUTRIENT_DEFINITIONS
            if (value := getattr(food.nutrients, key)) is not None
        }
        with localcontext(ARITHMETIC):
            grams, portion, unit_issue = _edible_weight(food, quantity, normalize_food_label(item.unit or ""))
            if unit_issue:
                reasons += (unit_issue,)
            provenance = NutritionProvenance(
                food_id=food.food_id, fdc_id=food.source.fdc_id, reference_version=self.reference.reference_version,
                source_release=self.reference.source.release, source_url=food.source.url, state=food.state,
                nutrient_source_row_ids=source_rows, portion_source_row_id=portion.source_row_id if portion else None,
            )
            if grams is None:
                return ItemNutritionResult(
                    name=item.name, status="not_calculable", provenance=provenance,
                    reasons=reasons, limitations=food.limitations,
                )

            values = {}
            for key in NUTRIENT_DEFINITIONS:
                nutrient = getattr(food.nutrients, key)
                values[key] = nutrient.amount * grams / 100 if nutrient is not None else None
            if len(source_rows) != len(NUTRIENT_DEFINITIONS):
                reasons += ("nutrient_data_missing",)
            status = "calculated" if not reasons else "partial" if source_rows else "not_calculable"
            limitation = (
                portion.applicability if portion else "Logged mass is treated as edible weight for the matched food state."
            )
            return ItemNutritionResult(
                name=item.name, status=status, nutrients=NutrientEstimates(**values), edible_grams=grams,
                conversion="reference_portion" if portion else "edible_mass", provenance=provenance,
                reasons=reasons, limitations=(*food.limitations, limitation),
            )


def _quantity(value: float | None) -> tuple[Decimal | None, NutritionReason | None]:
    if value is None:
        return None, "quantity_unknown"
    if type(value) not in (int, float):
        return None, "invalid_quantity"
    amount = Decimal(value) if type(value) is int else Decimal(str(value))
    if not amount.is_finite() or amount <= 0:
        return None, "invalid_quantity"
    return amount, None


def _edible_weight(
    food: NutritionFood, quantity: Decimal | None, unit: str,
) -> tuple[Decimal | None, UsdaPortion | None, NutritionReason | None]:
    if quantity is None:
        return None, None, None
    portion = None
    if unit in MASS_FACTORS:
        grams = quantity * MASS_FACTORS[unit]
    elif unit in HOUSEHOLD_UNITS or unit in PORTION_UNITS:
        row_id = PORTION_UNITS.get(unit, {}).get(food.food_id)
        portion = next((entry for entry in food.portions if entry.source_row_id == row_id), None)
        if portion is None:
            return None, None, "unsupported_serving_conversion"
        grams = quantity * portion.edible_grams / portion.amount
    else:
        return None, None, "unsupported_unit"
    if grams > MAX_EDIBLE_GRAMS:
        return None, None, "portion_needs_review"
    return grams, portion, None


def aggregate_nutrition(items: Iterable[ItemNutritionResult]) -> NutritionAggregate:
    """Sum estimates for supplied items. The caller owns record eligibility and date selection."""
    rows = tuple(items)
    calculated = sum(row.status != "not_calculable" for row in rows)
    full = sum(row.status == "calculated" for row in rows)
    subtotals = {}
    with localcontext(ARITHMETIC):
        for key, (_, _, unit) in NUTRIENT_DEFINITIONS.items():
            values = [
                value for row in rows if row.status != "not_calculable"
                and (value := getattr(row.nutrients, key)) is not None
            ]
            subtotals[key] = NutrientSubtotal(
                unit=unit, subtotal=sum(values, Decimal(0)) if values else None,
                contributing_items=len(values), missing_items=len(rows) - len(values),
            )
    if not rows:
        status = "no_items"
    elif not calculated:
        status = "not_calculable"
    elif full == len(rows):
        status = "all_logged_items_calculated"
    else:
        status = "partial"
    return NutritionAggregate(
        status=status, item_count=len(rows), calculated_item_count=calculated,
        fully_calculated_item_count=full, uncalculated_item_count=len(rows) - calculated,
        nutrients=NutritionSubtotals(**subtotals),
    )
