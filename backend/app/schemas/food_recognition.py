from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.schemas.food_logs import (
    Description, FoodItem, FoodLogInput, ShortText, require_nonblank_description,
)


class FoodRecognitionRequest(FoodLogInput):
    description: Description
    _require_description = field_validator("description")(require_nonblank_description)


class QuotedFoodItem(FoodLogInput):
    name: ShortText
    evidence: Annotated[str, Field(min_length=1, max_length=600)]
    portion_text: ShortText | None
    preparation_method: ShortText | None


class QuotedFoods(FoodLogInput):
    items: Annotated[list[QuotedFoodItem], Field(max_length=50)]
    needs_clarification: bool


class ProposedFoodItem(FoodItem):
    portion_note: Literal["quantity_unspecified", "portion_needs_review"] | None = None


class FoodRecognitionResponse(FoodLogInput):
    description: Description
    source: Literal["ai_text"] = "ai_text"
    status: Literal["draft"] = "draft"
    items: list[ProposedFoodItem]
    notes: list[Literal["no_identifiable_foods", "description_needs_review"]]
