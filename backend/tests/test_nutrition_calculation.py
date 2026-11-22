from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from app.schemas.food_logs import FoodItem
from app.schemas.nutrition_calculation import NutrientEstimates
from app.schemas.nutrition_reference import FDC_URL, NutrientsPer100g, NutritionReference
from app.services.nutrition_calculation import NutritionCalculator, aggregate_nutrition
from app.services.nutrition_reference import load_nutrition_reference


@pytest.fixture(scope="module")
def reference():
    return load_nutrition_reference()


@pytest.fixture(scope="module")
def calculator(reference):
    return NutritionCalculator(reference)


def item(name, quantity=100, unit="g", preparation=None):
    return FoodItem(name=name, quantity=quantity, unit=unit, preparation_method=preparation)


def test_known_gram_calculation_preserves_values_and_source(calculator):
    result = calculator.calculate_item(item("  COOKED  long-grain brown rice  ", 150, "Ｇ"))
    assert result.status == "calculated" and result.reasons == ()
    assert result.conversion == "edible_mass"
    assert result.edible_grams == 150
    assert result.nutrients == NutrientEstimates(
        energy_kcal="184.50", protein_g="4.11", carbohydrate_g="38.37", fat_g="1.455",
    )
    assert result.provenance is not None
    assert result.provenance.food_id == "brown_rice_long_grain_cooked"
    assert result.provenance.fdc_id == 169704
    assert result.provenance.source_url == FDC_URL.format(fdc_id=169704)
    assert result.provenance.reference_version == "usda-sr-legacy-v1"
    assert result.provenance.source_release == "2018-04"
    assert result.provenance.nutrient_source_row_ids == {
        "energy_kcal": 1462903, "protein_g": 1462868, "carbohydrate_g": 1462902, "fat_g": 1462901,
    }


@pytest.mark.parametrize("name,preparation,reason", [
    ("鸡胸肉", None, "food_state_unknown"),
    ("鸡胸肉", "生", "ambiguous_food_match"),
    ("去皮去骨鸡胸肉", "熟", "ambiguous_food_match"),
    ("去皮去骨鸡胸肉", "煎", "food_preparation_mismatch"),
    ("去皮去骨鸡胸肉（生）", "烤", "food_preparation_mismatch"),
    ("烤鸡胸肉（仅肉）", "炖", "food_preparation_mismatch"),
    ("熟长粒糙米", "生", "food_preparation_mismatch"),
    ("熟长粒糙米", "炒", "food_preparation_mismatch"),
    ("青菜", None, "ambiguous_food_match"),
    ("豆腐", None, "ambiguous_food_match"),
    ("番茄炒蛋", None, "mixed_dish_unsupported"),
    ("鸡肉配米饭和酱汁", None, "food_not_found"),
])
def test_unresolved_or_conflicting_food_is_never_substituted(calculator, name, preparation, reason):
    result = calculator.calculate_item(item(name, preparation=preparation))
    assert result.status == "not_calculable" and result.reasons == (reason,)
    assert result.provenance is None and result.edible_grams is None
    assert result.nutrients == NutrientEstimates()


@pytest.mark.parametrize("name,preparation,fdc_id,state,energy", [
    ("去皮去骨鸡胸肉", "生", 171077, "raw", 120),
    ("去皮去骨鸡胸肉", "烤", 171477, "cooked", 165),
    ("roasted skinless boneless chicken breast", "roasted", 171477, "cooked", 165),
    ("skinless boneless chicken breast", "stewed", 171478, "cooked", 151),
    ("米粉（干）", "干", 169742, "dry", 364),
    ("rice noodles", "cooked", 168914, "cooked", 108),
])
def test_explicit_compatible_preparations_select_exact_state(calculator, name, preparation, fdc_id, state, energy):
    result = calculator.calculate_item(item(name, preparation=preparation))
    assert result.status == "calculated"
    assert result.provenance is not None
    assert result.provenance.fdc_id == fdc_id and result.provenance.state == state
    assert result.nutrients.energy_kcal == energy


@pytest.mark.parametrize("quantity,unit,reason", [
    (None, "g", "quantity_unknown"),
    (0.5, "碗", "unsupported_serving_conversion"),
    (1, "cups", "unsupported_serving_conversion"),
    (1, "usda large egg", "unsupported_serving_conversion"),
    (1, None, "unsupported_unit"),
    (1, "scoop", "unsupported_unit"),
    (1, "g gross", "unsupported_unit"),
    (1e100, "kg", "portion_needs_review"),
])
def test_unknown_invalid_or_unverified_portions_are_not_estimated(calculator, quantity, unit, reason):
    result = calculator.calculate_item(item("熟长粒糙米", quantity, unit))
    assert result.status == "not_calculable" and result.reasons == (reason,)
    assert result.provenance is not None and result.provenance.fdc_id == 169704
    assert result.edible_grams is None and result.nutrients == NutrientEstimates()


@pytest.mark.parametrize("quantity", [-1, 0, "100", True, float("nan"), float("inf"), []])
def test_invalid_quantities_are_rejected_even_if_model_validation_was_bypassed(calculator, quantity):
    with pytest.raises(ValidationError):
        item("熟长粒糙米", quantity)
    unchecked = FoodItem.model_construct(name="熟长粒糙米", quantity=quantity, unit="g")
    result = calculator.calculate_item(unchecked)
    assert result.status == "not_calculable" and result.reasons == ("invalid_quantity",)
    assert result.edible_grams is None


def test_only_exact_food_specific_portion_is_accepted(calculator):
    result = calculator.calculate_item(item("全熟白煮蛋（去壳）", 1.5, "美标大号鸡蛋"))
    assert result.status == "calculated" and result.conversion == "reference_portion"
    assert result.edible_grams == 75
    assert result.nutrients.energy_kcal == Decimal("116.25")
    assert result.provenance is not None and result.provenance.portion_source_row_id == 92500
    assert "without shell" in result.limitations[-1]
    raw = calculator.calculate_item(item("生全蛋（去壳）", 1, "USDA large egg"))
    assert raw.provenance is not None and raw.provenance.portion_source_row_id == 88374
    generic = calculator.calculate_item(item("全熟白煮蛋（去壳）", 1, "个"))
    assert generic.reasons == ("unsupported_serving_conversion",)


def test_aggregate_keeps_partial_coverage_and_sums_unrounded_values(calculator):
    inputs = [
        item("熟长粒糙米", 0.15, "kg"),
        item("全熟水煮鸡蛋（去壳）", 1, "USDA large egg"),
        item("熟长粒糙米", 0.5, "碗"),
        item("青菜", None, None),
    ]
    estimates = [calculator.calculate_item(food) for food in inputs]
    summary = aggregate_nutrition(iter(estimates))
    assert summary.status == "partial" and summary.day_completeness == "not_assessed"
    assert (summary.item_count, summary.calculated_item_count, summary.fully_calculated_item_count,
            summary.uncalculated_item_count) == (4, 2, 2, 2)
    assert summary.nutrients.energy_kcal.subtotal == Decimal("262")
    assert summary.nutrients.protein_g.subtotal == Decimal("10.40")
    assert summary.nutrients.carbohydrate_g.subtotal == Decimal("38.93")
    assert summary.nutrients.fat_g.subtotal == Decimal("6.760")
    assert summary.nutrients.fat_g.contributing_items == 2
    assert summary.nutrients.fat_g.missing_items == 2
    assert estimates[-1].reasons == ("ambiguous_food_match", "quantity_unknown")
    with localcontext() as context:
        context.prec = 3
        assert [calculator.calculate_item(food) for food in inputs] == estimates
        assert aggregate_nutrition(estimates) == summary


def test_complete_coverage_of_supplied_items_does_not_assess_day(calculator):
    result = calculator.calculate_item(item("熟长粒糙米"))
    summary = aggregate_nutrition([result])
    assert summary.status == "all_logged_items_calculated"
    assert summary.day_completeness == "not_assessed"
    assert aggregate_nutrition([]).status == "no_items"
    unavailable = aggregate_nutrition([calculator.calculate_item(item("青菜"))])
    assert unavailable.status == "not_calculable"
    assert unavailable.nutrients.energy_kcal.subtotal is None


def test_synthetic_reference_distinguishes_missing_and_real_zero(reference):
    # Synthetic amounts only. The production snapshot and its source IDs are untouched.
    data = reference.model_dump()
    fixture = data["foods"][0]
    fixture.update(food_id="synthetic_raw", names={"zh_cn": "测试食物（生）", "en_us": "Synthetic food (raw)"}, aliases=())
    fixture["source"].update(fdc_id=999001, url=FDC_URL.format(fdc_id=999001), description="Synthetic food, raw")
    fixture["nutrients"] = {
        "energy_kcal": None, "protein_g": None, "carbohydrate_g": {"amount": 0, "source_row_id": 1},
        "fat_g": {"amount": 3.5, "source_row_id": 2},
    }
    data["foods"] = (fixture,)
    synthetic = NutritionReference.model_validate(data)
    result = NutritionCalculator(synthetic).calculate_item(item("Synthetic food (raw)", 125))
    assert result.status == "partial" and result.reasons == ("nutrient_data_missing",)
    assert result.nutrients == NutrientEstimates(carbohydrate_g=0, fat_g="4.375")
    summary = aggregate_nutrition([result])
    assert summary.status == "partial"
    assert summary.nutrients.energy_kcal.subtotal is None and summary.nutrients.energy_kcal.missing_items == 1
    assert summary.nutrients.carbohydrate_g.subtotal == 0 and summary.nutrients.carbohydrate_g.contributing_items == 1

    empty_nutrients = NutrientsPer100g(energy_kcal=None, protein_g=None, carbohydrate_g=None, fat_g=None)
    no_values = synthetic.foods[0].model_copy(update={"nutrients": empty_nutrients})
    none_calculated = NutritionCalculator(synthetic.model_copy(update={"foods": (no_values,)})).calculate_item(
        item("Synthetic food (raw)"),
    )
    assert none_calculated.status == "not_calculable"
    assert none_calculated.reasons == ("nutrient_data_missing",)
