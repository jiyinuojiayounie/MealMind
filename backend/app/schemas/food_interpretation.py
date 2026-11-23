from decimal import Decimal
from typing import Literal

from app.schemas.food_logs import FoodItem
from app.schemas.food_normalization import FoodNormalizationResult, PortionIssue
from app.schemas.nutrition_reference import ReferenceRecord

AmountContext = Literal["purchased", "prepared", "cooking_input", "cooked", "served",
                        "leftover", "discarded", "consumed", "unknown"]
WeighingState = Literal["raw", "dry", "cooked"]


class SourceSpan(ReferenceRecord):
    start: int
    end: int
    text: str


class PortionObservation(ReferenceRecord):
    quantity: Decimal
    unit: str
    span: SourceSpan
    context: AmountContext
    weighing_state: WeighingState | None = None
    basis: Literal["stated_edible", "includes_inedible", "unknown"] = "unknown"


class FoodMention(ReferenceRecord):
    source: SourceSpan
    identity_expression: str | None
    preparation: str | None = None
    preparation_evidence: tuple[SourceSpan, ...] = ()
    observations: tuple[PortionObservation, ...] = ()
    clarification: tuple[str, ...] = ()
    portion_issue: PortionIssue | None = None


class FoodInterpretation(ReferenceRecord):
    original: str
    status: Literal["interpreted", "review_required", "no_consumption"]
    mentions: tuple[FoodMention, ...] = ()


class InterpretedMatch(ReferenceRecord):
    mention: FoodMention
    proposal: FoodItem | None = None
    reference_match: FoodNormalizationResult | None = None
    portion_status: Literal["needs_review", "quantity_unknown", "conversion_unavailable", "verified_conversion", "edible_mass"]


class FoodInterpretationPreview(ReferenceRecord):
    interpretation: FoodInterpretation
    items: tuple[InterpretedMatch, ...] = ()
