from datetime import date

from app.schemas.daily_nutrition import DailyNutritionAnalysis, IndexedItemNutrition, LogNutritionAnalysis
from app.schemas.food_logs import FoodLog
from app.schemas.nutrition_calculation import NutritionReason
from app.services.nutrition_calculation import NutritionCalculator, aggregate_nutrition

REVIEW_GUIDANCE: dict[NutritionReason, str] = {
    "food_reference_binding_invalid": "The saved food reference could not be verified.",
    "food_reference_binding_stale": "The food details no longer match the saved reference confirmation.",
    "food_reference_binding_version_unavailable": "The reference catalog version for this confirmation is unavailable.",
    "food_not_found": "No matching reference is available for this food.",
    "ambiguous_food_match": "Review the food name, variety, and preparation.",
    "food_state_unknown": "Check whether the logged amount refers to raw, dry, or cooked food.",
    "food_preparation_mismatch": "Check whether the logged preparation matches a supported reference.",
    "mixed_dish_unsupported": "A matching mixed-dish reference is required. Unknown ingredients are not estimated.",
    "quantity_unknown": "Review the amount eaten if the edible quantity is known.",
    "invalid_quantity": "Review the logged quantity. It must be a positive finite number.",
    "portion_needs_review": "Check the portion size and unit against the amount eaten.",
    "unsupported_unit": "Check the logged unit. An edible weight in grams can be used when known.",
    "unsupported_serving_conversion": "No reviewed conversion matches this food and portion. Use edible grams if known.",
    "nutrient_data_missing": "The reference does not contain a value for every requested nutrient.",
}


def analyze_confirmed_logs(
    logs: list[FoodLog], consumed_on: date, calculator: NutritionCalculator,
) -> DailyNutritionAnalysis:
    analyses = []
    seen_ids = set()
    for log in logs:
        if log.id in seen_ids or log.status != "confirmed" or log.consumed_at.date() != consumed_on:
            raise ValueError("Analysis requires distinct confirmed logs for the requested date.")
        seen_ids.add(log.id)
        items = tuple(
            IndexedItemNutrition(
                item_index=index,
                **calculator.calculate_item(item, recognition_weight_review=log.recognition_weight_review).model_dump(),
            )
            for index, item in enumerate(log.items)
        )
        analyses.append(LogNutritionAnalysis(
            log_id=log.id, revision=log.revision, meal_type=log.meal_type,
            consumed_at=log.consumed_at, items=items, summary=aggregate_nutrition(items),
        ))

    items = tuple(item for log in analyses for item in log.items)
    summary = aggregate_nutrition(items)
    reasons = {reason for item in items for reason in item.reasons}
    return DailyNutritionAnalysis(
        **summary.model_dump(exclude={"status"}),
        status="no_confirmed_logs" if summary.status == "no_items" else summary.status,
        date=consumed_on, confirmed_log_count=len(analyses), logs=tuple(analyses),
        reference_version=calculator.reference.reference_version, reference_source=calculator.reference.source,
        review_guidance={reason: REVIEW_GUIDANCE[reason] for reason in sorted(reasons)},
    )
