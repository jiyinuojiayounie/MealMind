from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.food_logs import (
    Description, FoodItem, FoodLogInput, RecognitionEvidence, ShortText, require_nonblank_description,
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
    recognition_evidence: RecognitionEvidence | None = Field(default=None, exclude_if=lambda value: value is None)
    portion_note: Literal["quantity_unspecified", "portion_needs_review"] | None = None


class CookingOilEvidence(FoodLogInput):
    quote: ShortText
    portion_text: ShortText


class FoodRecognitionResponse(FoodLogInput):
    cooking_evidence: list[CookingOilEvidence] = Field(default_factory=list, exclude_if=lambda value: not value)
    description: Description
    source: Literal["ai_text"] = "ai_text"
    status: Literal["draft"] = "draft"
    items: list[ProposedFoodItem]
    notes: list[Literal["no_identifiable_foods", "description_needs_review"]]


VisibleUnit = Literal["个", "片", "块", "根"]


class VisibleFood(FoodLogInput):
    name: ShortText
    identity_uncertain: Annotated[bool, Field(strict=True)]
    count: Annotated[int, Field(strict=True, ge=1, le=50)] | None
    count_unit: VisibleUnit | None

    @model_validator(mode="after")
    def validate_count(self):
        if (self.count is None) != (self.count_unit is None):
            raise ValueError("A visible count and its unit must be supplied together")
        return self


class VisibleFoods(FoodLogInput):
    items: Annotated[list[VisibleFood], Field(max_length=50)]
    needs_review: Annotated[bool, Field(strict=True)]


class ImageProposedFoodItem(ProposedFoodItem):
    identity_uncertain: bool


class ImageFoodRecognitionResponse(FoodLogInput):
    description: None = None
    source: Literal["ai_image"] = "ai_image"
    status: Literal["draft"] = "draft"
    items: list[ImageProposedFoodItem]
    notes: list[Literal["no_identifiable_foods", "image_needs_review"]]
