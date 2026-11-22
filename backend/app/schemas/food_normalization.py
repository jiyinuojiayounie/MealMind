from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StrictBool

from app.schemas.food_logs import FoodItem, FoodLogInput

from app.schemas.nutrition_reference import FoodNames, ReferenceRecord, Text

IdentityStatus = Literal[
    "matched", "ambiguous_identity", "food_state_unknown", "unsupported_food", "insufficient_information",
]
PortionStatus = Literal["edible_mass", "verified_conversion", "quantity_unknown", "conversion_unavailable", "needs_review"]
FoodState = Literal["raw", "cooked", "dry", "as_sold"]


class AmbiguousAlias(ReferenceRecord):
    labels: tuple[Text, ...]
    reason: Text
    candidates: tuple[Text, ...]


class FoodAliasIndex(ReferenceRecord):
    version: Literal["food-aliases-v1"]
    reference_version: Text
    exact_aliases: dict[str, tuple[Text, ...]]
    qualified_aliases: dict[str, dict[str, str]]
    ambiguous_aliases: tuple[AmbiguousAlias, ...]
    unsupported_labels: tuple[Text, ...]


class FoodCandidate(ReferenceRecord):
    food_id: str
    fdc_id: int
    names: FoodNames
    state: FoodState
    preparation: str
    source_url: str


class FoodNormalizationResult(ReferenceRecord):
    original: str
    food_label: str
    preparation: str | None = None
    food_state: FoodState | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    portion_status: PortionStatus
    requires_edible_weight_confirmation: bool
    portion_source_row_id: int | None = None
    identity_status: IdentityStatus
    reference: FoodCandidate | None = None
    matched_rule: str | None = None
    matched_alias: str | None = None
    candidates: tuple[FoodCandidate, ...] = ()
    clarification: str | None = None
    reference_version: str
    source_release: str
    alias_version: str


class FoodMatchingItem(FoodLogInput):
    item: FoodItem
    identity_uncertain: StrictBool = False


class FoodMatchingPreview(FoodLogInput):
    items: Annotated[list[FoodMatchingItem], Field(min_length=1, max_length=50)]
