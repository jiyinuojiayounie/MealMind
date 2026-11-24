from datetime import date as CalendarDate
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, StringConstraints, model_validator

from app.core.calendar import parse_calendar_date
from app.schemas.meal_plans import MealPlanResponse, MealType, Minutes, Name, PlannedMeal, StructuredOutput

LocalDate = Annotated[CalendarDate, BeforeValidator(parse_calendar_date)]
TimeZoneName = Annotated[str, StringConstraints(min_length=1, max_length=100)]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
PlanningMode = Literal["prompt_only", "catalog"]
Revision = Annotated[int, Field(ge=1, le=9_007_199_254_740_991)]


class PlanSnapshot(MealPlanResponse):
    additional_ingredients: Annotated[list[Name], Field(max_length=320)]

    @model_validator(mode="after")
    def validate_slots(self):
        slots = {meal.meal_type for meal in self.meals}
        if len(slots) != len(self.meals):
            raise ValueError("Invalid accepted plan meal slots")
        return self


class AcceptedPlan(StructuredOutput):
    plan_id: Annotated[UUID, Field(strict=False)]
    revision: Revision
    date: LocalDate
    source: Literal["prompt_only", "catalog", "blind_box"]
    plan: PlanSnapshot


class ReplanConstraints(StructuredOutput):
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    ingredient_mode: Literal["existing", "flexible"] = "flexible"
    available_ingredients: Annotated[list[Name], Field(max_length=60)] = Field(default_factory=list)
    cooking_time_limit: Minutes | None = None
    prefer_low_effort: bool = False
    one_person: bool = True
    restriction_status: Literal["unreviewed", "none_declared", "present"] = "unreviewed"


class ReplanRequest(StructuredOutput):
    date: LocalDate
    timezone: TimeZoneName
    target_meal_type: MealType
    expected_context_fingerprint: Fingerprint
    current_plan: AcceptedPlan | None = None
    planning_mode: PlanningMode | None = None
    constraints: ReplanConstraints
    instructions: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1900)] = ""

    @model_validator(mode="after")
    def validate_plan_date(self):
        if self.current_plan and self.current_plan.date != self.date:
            raise ValueError("Accepted plan date must match the requested date")
        return self


class ReplanContext(StructuredOutput):
    date: CalendarDate
    date_basis: Literal["recorded_offset"] = "recorded_offset"
    context_fingerprint: Fingerprint
    confirmed_log_count: int
    confirmed_by_meal_type: dict[MealType, int]
    unspecified_log_count: int
    locked_meal_types: tuple[MealType, ...]
    remaining_main_meal_types: tuple[MealType, ...]
    day_completeness: Literal["not_assessed"] = "not_assessed"


class ReplanPreview(StructuredOutput):
    proposal_id: UUID
    status: Literal["preview"] = "preview"
    date: CalendarDate
    timezone: TimeZoneName
    target_meal_type: MealType
    source: PlanningMode
    current_meal: PlannedMeal | None
    suggested_plan: MealPlanResponse
    untouched_meal_types: tuple[MealType, ...]
    base_plan_id: UUID | None
    base_plan_revision: Revision | None
    context: ReplanContext
    context_fingerprint: Fingerprint
    variety_match_count: int
    uncertainty: tuple[str, ...]
