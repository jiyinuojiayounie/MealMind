import math
import re
from fractions import Fraction

from app.core.settings import Settings
from app.prompts.food_recognition import FOOD_RECOGNITION_INSTRUCTIONS
from app.schemas.food_recognition import (
    FoodRecognitionRequest, FoodRecognitionResponse, ProposedFoodItem, QuotedFoods,
)
from app.services.meal_plans import PlannerFailure, generate_structured

ENGLISH_NUMBERS = {
    word: index for index, word in enumerate("one two three four five six seven eight nine ten".split(), start=1)
}
ENGLISH_NUMBERS.update(a=1, an=1, half=0.5)
CHINESE_NUMBERS = dict(zip("一二三四五六七八九十两半", (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 2, 0.5)))
NUMBER = r"[0-9]+(?:\.[0-9]+|/[0-9]+)?"
ENGLISH_NUMBER = "|".join(ENGLISH_NUMBERS)
UNIT = (
    r"g|kg|mg|ml|l|oz|lbs?|grams?|kilograms?|milliliters?|liters?|ounces?|pounds?"
    r"|bowls?|cups?|tablespoons?|teaspoons?|tbsp|tsp|slices?|pieces?|handfuls?|servings?|sticks?"
    r"|小把|大把|克|公克|千克|公斤|毫升|升|碗|根|把|勺|汤匙|茶匙|杯|片|块|个|颗|份|条|瓶|包"
)
PORTION = re.compile(
    rf"(?P<number>{NUMBER}|[{''.join(CHINESE_NUMBERS)}]|{ENGLISH_NUMBER})"
    rf"(?:\s+a\s+)?\s*(?P<unit>{UNIT})?", re.IGNORECASE,
)
UNCERTAIN_PREFIX = re.compile(r"(?:约|大概|近|[~～<>≤≥]|\b(?:about|roughly|around|approximately|under|over)\s*)$", re.I)


def _parse_portion(portion: str, evidence: str, description: str) -> tuple[float, str | None] | None:
    match = PORTION.fullmatch(portion)
    if match is None:
        return None
    offset = description.index(evidence) + evidence.index(portion)
    raw_before, raw_after = description[:offset], description[offset + len(portion):]
    if re.search(r"\d[./]?$", raw_before) or re.match(r"(?:[./]?\d)", raw_after):
        return None
    if match["unit"] is None and re.match(rf"\s*(?:{UNIT})(?![a-z])", raw_after, re.I):
        return None
    before, after = raw_before.rstrip(), raw_after.lstrip()
    if UNCERTAIN_PREFIX.search(before) or before.endswith(("-", "–", "—", "至", "到")) or (
        re.match(r"[-–—至到]\s*(?:[0-9]|[一二三四五六七八九十两半])", after)
    ):
        return None
    token = match["number"].casefold()
    unit = match["unit"]
    if token in ENGLISH_NUMBERS or token in CHINESE_NUMBERS:
        quantity = ENGLISH_NUMBERS.get(token, CHINESE_NUMBERS.get(token))
        if unit is None or quantity is None:
            return None
        return float(quantity), unit
    try:
        quantity = float(Fraction(token))
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    if math.isfinite(quantity) and quantity > 0:
        return quantity, unit
    return None


def recognize_food_text(request: FoodRecognitionRequest, settings: Settings) -> FoodRecognitionResponse:
    proposed = generate_structured(
        settings, contents=request.model_dump_json(), instructions=FOOD_RECOGNITION_INSTRUCTIONS,
        response_model=QuotedFoods, max_output_tokens=4096,
    )
    items = []
    seen = set()
    for item in proposed.items:
        if (
            item.evidence not in request.description or item.name not in item.evidence
            or (item.preparation_method is not None and item.preparation_method not in item.evidence)
            or (item.portion_text is not None and item.portion_text not in item.evidence)
        ):
            raise PlannerFailure
        key = (item.evidence, item.name)
        if key in seen:
            raise PlannerFailure
        seen.add(key)
        parsed = _parse_portion(item.portion_text, item.evidence, request.description) if item.portion_text else None
        quantity, unit = parsed if parsed else (None, None)
        items.append(ProposedFoodItem(
            name=item.name, quantity=quantity, unit=unit, preparation_method=item.preparation_method,
            portion_note=None if parsed else ("portion_needs_review" if item.portion_text else "quantity_unspecified"),
        ))
    notes = []
    if not items:
        notes.append("no_identifiable_foods")
    if proposed.needs_clarification:
        notes.append("description_needs_review")
    return FoodRecognitionResponse(description=request.description, items=items, notes=notes)
