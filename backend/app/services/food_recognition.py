import math
import re
from fractions import Fraction

from google.genai import types

from app.core.settings import Settings
from app.prompts.food_recognition import FOOD_RECOGNITION_INSTRUCTIONS, IMAGE_RECOGNITION_INSTRUCTIONS
from app.schemas.food_logs import FoodItemDraft, RecognitionEvidence
from app.schemas.food_recognition import (
    CookingOilEvidence, FoodRecognitionRequest, FoodRecognitionResponse, ImageFoodRecognitionResponse, ImageProposedFoodItem,
    ProposedFoodItem, QuotedFoods, VisibleFoods,
)
from app.services.food_images import normalize_image
from app.services.meal_plans import PlannerFailure, generate_structured
from app.services.portion_evidence import portion_context_issue

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


# This evidence is not a food item. Keep the pattern limited to an affirmed cooking-use clause.
_COOKING_OIL = re.compile(
    r"(?:炒菜|做菜|烹饪|烹調)用了\s*(?P<portion>\d+(?:\.\d+)?\s*(?:g|克|公克))\s*"
    r"(?P<oil>食用油|菜籽油|橄榄油|花生油|油)(?=$|[\s，,。.;；！？]|但|剩)", re.I,
)
_CLAUSE_BREAK = re.compile(r"[，,；;]")
_SENTENCE_BREAK = re.compile(r"[。!?！？\n]|\.(?=\s|$)")
_WEIGHING_TEXT = re.compile(
    r"生重|熟重|干重|按可食部分称重|\b(?:raw weight|cooked weight|dry weight|"
    r"weighed raw|weighed cooked|edible weight)\b", re.I,
)
_INTAKE = re.compile(r"吃了|喝了|吃下|吃掉|\b(?:ate|drank|consumed)\b", re.I)
_SERVED = re.compile(r"盛了|上桌|\bserved\b", re.I)
_NOT_EATEN = re.compile(r"没(?:有)?吃(?!完)|不吃|想吃|准备吃|\b(?:did not|didn['’]t|will|plan to|want to) eat\b", re.I)


def _portion_evidence(description: str, quote: str, portion: str | None, name: str, preparation: str | None):
    offset = description.index(quote)
    left = _SENTENCE_BREAK.split(description[:offset])[-1]
    right = _SENTENCE_BREAK.split(description[offset + len(quote):], maxsplit=1)[0]
    preceding = list(_CLAUSE_BREAK.finditer(left))
    if preceding and _COOKING_OIL.search(left[:preceding[-1].start()]) and _INTAKE.search(left[preceding[-1].end():]):
        left = left[preceding[-1].end():]
    sentence = left + quote + right
    cooking = _COOKING_OIL.search(right)
    if cooking:
        separators = list(_CLAUSE_BREAK.finditer(right, 0, cooking.start()))
        if separators and _INTAKE.search(left + quote):
            # A separately stated consumed food keeps its own explicit amount.
            sentence = left + quote + right[:separators[-1].start()]
    issue = portion_context_issue(sentence)
    context = issue or ("served" if _SERVED.search(sentence) else "consumed" if _INTAKE.search(sentence) else "unknown")
    # Attribute the quoted number to its governing clause even when a later clause
    # explains why it is unsuitable (for example, oil used and then left behind).
    amount_context = portion_context_issue(left + quote)
    if amount_context in {"cooking_input", "purchased_or_prepared"}:
        context = amount_context
    measuring = _WEIGHING_TEXT.search(sentence)
    reason = None
    parsed = None
    if portion:
        if description.count(quote) != 1 or quote.count(portion) != 1:
            reason = "ambiguous_quote"
        elif issue or context == "served" or _NOT_EATEN.search(sentence):
            reason = issue or ("served" if context == "served" else "consumption_unclear")
        else:
            parsed = _parse_portion(portion, quote, description)
            if parsed is None:
                reason = "amount_needs_review"
    evidence = RecognitionEvidence(
        name=name, preparation_method=preparation, quote=quote, portion_text=portion, weighing_text=measuring[0] if measuring else None,
        context=context, decision="accepted" if parsed else "withheld" if portion else "unspecified", reason=reason,
    )
    return parsed, evidence


def validate_saved_recognition_evidence(item: FoodItemDraft, description: str | None) -> RecognitionEvidence | None:
    evidence = item.recognition_evidence
    if not evidence or not description or evidence.quote not in description or item.name not in evidence.quote:
        return None
    if item.preparation_method and item.preparation_method not in evidence.quote:
        return None
    if evidence.portion_text and evidence.portion_text not in evidence.quote:
        return None
    parsed, verified = _portion_evidence(description, evidence.quote, evidence.portion_text, item.name, item.preparation_method)
    if verified == evidence and (item.quantity, item.unit) == (parsed or (None, None)):
        return verified
    return None


_COOKING_ONLY_TAIL = re.compile(r"\s*(?:[，,]\s*(?:但)?锅里(?:还)?剩(?:一些|一点))?\s*[。.!！]?\s*")


def recognize_food_text(request: FoodRecognitionRequest, settings: Settings) -> FoodRecognitionResponse:
    description = request.description
    cooking_matches = [match for match in _COOKING_OIL.finditer(description) if len(match[0]) <= 120]
    cooking_evidence = [
        CookingOilEvidence(quote=match[0], portion_text=match["portion"]) for match in cooking_matches
    ]
    try:
        proposed = generate_structured(
            settings, contents=request.model_dump_json(), instructions=FOOD_RECOGNITION_INSTRUCTIONS,
            response_model=QuotedFoods, max_output_tokens=4096,
        )
        items = _recognized_items(description, proposed, cooking_matches)
    except PlannerFailure:
        # Recover only when the entire request is independently accounted for.
        # A mixed request could contain consumed foods that a failed response lost.
        if len(cooking_matches) != 1:
            raise
        match = cooking_matches[0]
        if description[:match.start()].strip() or not _COOKING_ONLY_TAIL.fullmatch(description[match.end():]):
            raise
        return FoodRecognitionResponse(
            description=description, items=[], notes=["no_identifiable_foods"], cooking_evidence=cooking_evidence,
        )

    notes = []
    if not items:
        notes.append("no_identifiable_foods")
    if proposed.needs_clarification:
        notes.append("description_needs_review")
    return FoodRecognitionResponse(
        description=description, items=items, notes=notes, cooking_evidence=cooking_evidence,
    )


def _recognized_items(
    description: str, proposed: QuotedFoods, cooking_matches: list[re.Match[str]],
) -> list[ProposedFoodItem]:
    items = []
    seen = set()
    for item in proposed.items:
        if (
            item.evidence not in description or item.name not in item.evidence
            or (item.preparation_method is not None and item.preparation_method not in item.evidence)
            or (item.portion_text is not None and item.portion_text not in item.evidence)
        ):
            raise PlannerFailure
        key = (item.evidence, item.name)
        if key in seen:
            raise PlannerFailure
        seen.add(key)
        parsed, evidence = _portion_evidence(
            description, item.evidence, item.portion_text, item.name, item.preparation_method,
        )
        start = description.index(item.evidence)
        end = start + len(item.evidence)
        if parsed is None and description.count(item.evidence) == 1 and any(
            item.name in match["oil"] and start < match.end("oil") and match.start("oil") < end
            for match in cooking_matches
        ):
            continue
        quantity, unit = parsed if parsed else (None, None)
        items.append(ProposedFoodItem(
            name=item.name, quantity=quantity, unit=unit, preparation_method=item.preparation_method,
            recognition_evidence=evidence,
            portion_note=None if parsed else ("portion_needs_review" if item.portion_text else "quantity_unspecified"),
        ))
    return items


def recognize_food_image(data: bytes, settings: Settings) -> ImageFoodRecognitionResponse:
    jpeg = normalize_image(data)
    visible = generate_structured(
        settings,
        contents=[types.Part.from_bytes(data=jpeg, mime_type="image/jpeg")],
        instructions=IMAGE_RECOGNITION_INSTRUCTIONS,
        response_model=VisibleFoods,
        max_output_tokens=4096,
    )
    items = [
        ImageProposedFoodItem(
            name=item.name,
            quantity=None if item.identity_uncertain else item.count,
            unit=None if item.identity_uncertain else item.count_unit,
            portion_note="portion_needs_review" if item.identity_uncertain or item.count is None else None,
            identity_uncertain=item.identity_uncertain,
        )
        for item in visible.items
    ]
    notes = []
    if not items:
        notes.append("no_identifiable_foods")
    if visible.needs_review or any(item.identity_uncertain for item in items):
        notes.append("image_needs_review")
    return ImageFoodRecognitionResponse(items=items, notes=notes)
