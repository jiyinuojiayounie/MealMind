"""Produce an offline comparison from the existing Python nutrition fixtures."""

import json

from scripts.export_browser_nutrition_rules import browser_rules
from tests.test_nutrition_calculation import (
    item, test_explicit_compatible_preparations_select_exact_state,
    test_unknown_invalid_or_unverified_portions_are_not_estimated,
    test_unresolved_or_conflicting_food_is_never_substituted,
)

from app.schemas.nutrition_reference import NutritionReference
from app.services.nutrition_calculation import NutritionCalculator, aggregate_nutrition


def parameters(test):
    return next(mark.args[1] for mark in test.pytestmark if mark.name == "parametrize")


def fixtures() -> dict:
    calculator = NutritionCalculator()
    foods = [
        item("  COOKED  long-grain brown rice  ", 150, "Ｇ"),
        item("熟长粒糙米", 0.15, "kg"),
        item("熟长粒糙米", 250000, "mg"),
        item("全熟白煮蛋（去壳）", 1.5, "美标大号鸡蛋"),
        item("全熟水煮鸡蛋（去壳）", 1, "USDA large egg"),
        item("生全蛋（去壳）", 1, "USDA large egg"),
        item("全熟白煮蛋（去壳）", 1, "个"),
        item("青菜", None, None),
        item("牛肉面"),
        item("蒸蛋"),
    ]
    foods.extend(item(name, preparation=preparation) for name, preparation, _ in
                 parameters(test_unresolved_or_conflicting_food_is_never_substituted))
    foods.extend(item(name, preparation=preparation) for name, preparation, *_ in
                 parameters(test_explicit_compatible_preparations_select_exact_state))
    foods.extend(item("熟长粒糙米", quantity, unit) for quantity, unit, _ in
                 parameters(test_unknown_invalid_or_unverified_portions_are_not_estimated))
    data = calculator.reference.model_dump(mode="json")
    synthetic = data["foods"][0]
    synthetic["nutrients"] = {
        "energy_kcal": None, "protein_g": None, "carbohydrate_g": {"amount": 0, "source_row_id": 1},
        "fat_g": {"amount": 3.5, "source_row_id": 2},
    }
    data["foods"] = [synthetic]
    fixture = NutritionReference.model_validate(data)
    synthetic_item = item(synthetic["names"]["en_us"], 125)

    def group(inputs, engine):
        results = [engine.calculate_item(food) for food in inputs]
        return {
            "inputs": [food.model_dump(mode="json") for food in inputs],
            "results": [result.model_dump(mode="json") for result in results],
            "aggregate": aggregate_nutrition(results).model_dump(mode="json"),
        }

    return {
        "rules": browser_rules(),
        "groups": [group(foods, calculator), group([synthetic_item], NutritionCalculator(fixture))],
        "synthetic": data,
    }


if __name__ == "__main__":
    print(json.dumps(fixtures(), ensure_ascii=False))
