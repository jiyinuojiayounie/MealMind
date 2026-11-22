from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

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


class FoodLogDraft(FoodLogInput):
    meal_type: MealType | Literal["unspecified"] = "unspecified"
    consumed_at: AwareDatetime
    description: Description | None = None
    items: Annotated[list[FoodItem], Field(min_length=1, max_length=50)]

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


class FoodLogConfirmation(FoodLogInput):
    expected_revision: Revision


class FoodLog(FoodLogCreate):
    id: UUID
    status: FoodLogStatus
    revision: Revision
    created_at: AwareDatetime
    updated_at: AwareDatetime
