from datetime import datetime
from typing import Literal

from app.schemas.food_logs import (
    FoodItem, FoodItemDraft, FoodReferenceBinding, FoodReferenceSelection, LoggedFoodItem,
)
from app.schemas.nutrition_reference import NutritionFood
from app.services.food_normalization import FoodNormalizer, get_food_normalizer
from app.services.food_recognition import validate_saved_recognition_evidence

BindingFailure = Literal["catalog_version_unavailable", "item_changed", "reference_not_applicable", "invalid_binding"]


class FoodReferenceBindingUnavailable(Exception):
    pass


class FoodReferenceBindingRejected(Exception):
    def __init__(self, item_index: int, reason: BindingFailure):
        self.item_index = item_index
        self.reason = reason


def item_fields(item: FoodItem) -> FoodItem:
    return FoodItem(name=item.name, quantity=item.quantity, unit=item.unit, preparation_method=item.preparation_method)


def resolve_selection(
    item: FoodItem, selection: FoodReferenceSelection, normalizer: FoodNormalizer,
) -> tuple[NutritionFood | None, BindingFailure | None]:
    if selection.reference_version != normalizer.reference.reference_version:
        return None, "catalog_version_unavailable"
    if item_fields(item) != selection.item:
        return None, "item_changed"
    preview = normalizer.match_item(item)
    if selection.food_id not in {candidate.food_id for candidate in preview.candidates} and (
        preview.reference is None or preview.reference.food_id != selection.food_id
    ):
        return None, "reference_not_applicable"
    return normalizer.foods[selection.food_id], None


def resolve_binding(
    item: LoggedFoodItem, normalizer: FoodNormalizer,
) -> tuple[NutritionFood | None, BindingFailure | None]:
    binding = item.reference_binding
    if not isinstance(binding, FoodReferenceBinding):
        return None, "invalid_binding"
    food, reason = resolve_selection(item, binding, normalizer)
    if food is None:
        return None, reason
    if (
        binding.fdc_id != food.source.fdc_id or binding.state != food.state
        or binding.preparation != food.preparation or binding.source_release != normalizer.reference.source.release
    ):
        return None, "invalid_binding"
    return food, None


def _normalizer_for_write() -> FoodNormalizer:
    try:
        return get_food_normalizer()
    except (OSError, ValueError):
        raise FoodReferenceBindingUnavailable from None


def bind_draft_items(items: list[FoodItemDraft], now: datetime, description: str | None = None) -> list[LoggedFoodItem]:
    bound = []
    for index, item in enumerate(items):
        selection = item.reference_binding
        binding = None
        if selection is not None:
            normalizer = _normalizer_for_write()
            food, reason = resolve_selection(item, selection, normalizer)
            if food is None:
                raise FoodReferenceBindingRejected(index, reason or "invalid_binding")
            binding = FoodReferenceBinding(
                **selection.model_dump(), binding_version="food-reference-binding-v1",
                state=food.state, preparation=food.preparation,
                fdc_id=food.source.fdc_id, source_release=normalizer.reference.source.release, confirmed_at=now,
            )
        bound.append(LoggedFoodItem(
            **item_fields(item).model_dump(), reference_binding=binding,
            recognition_evidence=validate_saved_recognition_evidence(item, description),
        ))
    return bound


def validate_bindings_for_confirmation(items: list[LoggedFoodItem]) -> None:
    for index, item in enumerate(items):
        if item.reference_binding is not None:
            _, reason = resolve_binding(item, _normalizer_for_write())
            if reason:
                raise FoodReferenceBindingRejected(index, reason)
