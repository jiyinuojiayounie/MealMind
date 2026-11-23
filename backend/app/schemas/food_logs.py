from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StringConstraints, ValidationError, field_validator

from app.schemas.meal_plans import MealType

FoodLogSource = Literal["manual_text", "ai_text", "ai_image"]
FoodLogStatus = Literal["draft", "confirmed"]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Revision = Annotated[int, Field(gt=0, strict=True)]
Description = Annotated[str, Field(min_length=1, max_length=2000)]


def require_nonblank_description(value: str) -> str:
    if not value.strip():
        raise ValueError("Description must not be blank")
    return value


class FoodLogInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FoodItem(FoodLogInput):
    name: ShortText
    quantity: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)] | None = None
    unit: ShortText | None = None
    preparation_method: ShortText | None = None


class RecognitionEvidence(FoodLogInput):
    name: ShortText
    preparation_method: ShortText | None = None
    quote: Annotated[str, Field(min_length=1, max_length=600)]
    portion_text: ShortText | None = None
    weighing_text: ShortText | None = None
    context: ShortText
    decision: Literal["accepted", "withheld", "unspecified"]
    reason: ShortText | None = None


class FoodReferenceSelection(FoodLogInput):
    food_id: ShortText
    reference_version: ShortText
    confirmed: StrictBool
    edible_weight_confirmed: StrictBool = False
    item: FoodItem

    @field_validator("confirmed")
    @classmethod
    def require_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("The food reference must be explicitly confirmed")
        return value


class FoodReferenceBinding(FoodReferenceSelection):
    binding_version: Literal["food-reference-binding-v1"]
    state: Literal["raw", "cooked", "dry", "as_sold"]
    preparation: ShortText
    fdc_id: Annotated[int, Field(gt=0, strict=True)]
    source_release: ShortText
    confirmed_at: AwareDatetime


class InvalidFoodReferenceBinding(FoodLogInput):
    status: Literal["invalid_binding"] = "invalid_binding"


class FoodItemDraft(FoodItem):
    recognition_evidence: RecognitionEvidence | None = None
    reference_binding: FoodReferenceSelection | None = None


class LoggedFoodItem(FoodItem):
    recognition_evidence: RecognitionEvidence | None = Field(default=None, exclude_if=lambda value: value is None)
    reference_binding: FoodReferenceBinding | InvalidFoodReferenceBinding | None = Field(
        default=None, exclude_if=lambda binding: binding is None,
    )

    @field_validator("reference_binding", mode="before")
    @classmethod
    def preserve_unreadable_binding_as_invalid(cls, value: object) -> object:
        if value is None:
            return None
        try:
            return FoodReferenceBinding.model_validate(value)
        except ValidationError:
            return InvalidFoodReferenceBinding()


class FoodLogDraft(FoodLogInput):
    meal_type: MealType | Literal["unspecified"] = "unspecified"
    consumed_at: AwareDatetime
    description: Description | None = None
    items: Annotated[list[FoodItemDraft], Field(min_length=1, max_length=50)]

    @field_validator("description", mode="before")
    @classmethod
    def normalize_empty_description(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("consumed_at", mode="before")
    @classmethod
    def require_timestamp(cls, value: object) -> object:
        if not isinstance(value, datetime) and (
            not isinstance(value, str) or len(value) < 16 or value[10] not in ("T", "t")
        ):
            raise ValueError("Use an ISO 8601 timestamp with a UTC offset")
        return value


class FoodLogCreate(FoodLogDraft):
    source: FoodLogSource = "manual_text"


class FoodLogUpdate(FoodLogDraft):
    expected_revision: Revision
    recognition_applied: StrictBool = False


class FoodLogConfirmation(FoodLogInput):
    expected_revision: Revision


class FoodLog(FoodLogCreate):
    recognition_weight_review: StrictBool = Field(default=False, exclude_if=lambda value: not value)
    items: Annotated[list[LoggedFoodItem], Field(min_length=1, max_length=50)]
    id: UUID
    status: FoodLogStatus
    revision: Revision
    created_at: AwareDatetime
    updated_at: AwareDatetime
