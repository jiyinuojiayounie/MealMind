from datetime import date as CalendarDate
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime

from app.schemas.meal_plans import MealType
from app.schemas.nutrition_calculation import ItemNutritionResult, NutritionAggregate, NutritionReason
from app.schemas.nutrition_reference import ReferenceRecord, UsdaRelease


class IndexedItemNutrition(ItemNutritionResult):
    item_index: int


class LogNutritionAnalysis(ReferenceRecord):
    log_id: UUID
    revision: int
    meal_type: MealType | Literal["unspecified"]
    consumed_at: AwareDatetime
    summary: NutritionAggregate
    items: tuple[IndexedItemNutrition, ...]


class DailyNutritionAnalysis(NutritionAggregate):
    status: Literal["no_confirmed_logs", "not_calculable", "partial", "all_logged_items_calculated"]
    date: CalendarDate
    date_basis: Literal["recorded_offset"] = "recorded_offset"
    reference_version: str
    reference_source: UsdaRelease
    confirmed_log_count: int
    logs: tuple[LogNutritionAnalysis, ...]
    review_guidance: dict[NutritionReason, str]
