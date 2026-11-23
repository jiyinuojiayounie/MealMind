"""Parse a bounded set of food expressions before the existing structured matcher."""

import math
import re
from decimal import Decimal

from app.schemas.food_interpretation import (
    AmountContext, FoodInterpretation, FoodInterpretationPreview, FoodMention, InterpretedMatch,
    PortionObservation, SourceSpan,
)
from app.schemas.food_logs import FoodItem
from app.schemas.food_normalization import PortionIssue
from app.services.food_normalization import NUMBER, UNITS, FoodNormalizer, _number, get_food_normalizer
from app.services.nutrition_units import MASS_FACTORS
from app.services.portion_evidence import portion_context_issue

OBSERVATION_UNITS = "|".join(sorted((*UNITS, "勺", "口", "包", "朵", "袋", "盒", "筷子"), key=len, reverse=True))
OBSERVATION = re.compile(
    rf"(?<![\da-z.+/\-])(?P<number>{NUMBER})(?:\s+a\s+)?\s*(?P<unit>{OBSERVATION_UNITS})(?![a-z])", re.I,
)
NO_INTAKE = re.compile(
    r"\s*(?:今天)?(?:没有|没)(?:吃|喝)(?:早饭|早餐|午饭|午餐|晚饭|晚餐|东西)?[。.!！]?\s*$"
    r"|\s*(?:i )?(?:skipped (?:breakfast|lunch|dinner)|didn['’]t eat(?: anything)?)[.!]?\s*$", re.I,
)
NON_ASSERTION = re.compile(
    r"没有吃|没吃|不想吃|想吃|打算|计划吃|(?:\b(?:did not|didn['’]t|might|will|want to|plan to) "
    r"(?:eat|have|drink)\b)|[?？]", re.I,
)
LEAD = re.compile(
    r"^(?:(?:今天|昨天|早餐|午饭|午餐|晚饭|晚餐|早上|中午|晚上)\s*)*(?:我\s*)?(?:吃了|喝了|吃掉了)\s*"
    r"|^(?:i\s+)?(?:ate|drank)\s+", re.I,
)
EATEN = re.compile(r"吃了|喝了|吃掉|吃下|生吃|\b(?:ate|drank|consumed)\b", re.I)
EDIBLE = re.compile(r"可食(?:部分)?|净肉|不含壳|只吃瓤|\b(?:edible|meat only|without shell)\b", re.I)
RANGE = re.compile(r"(?:\d\s*(?:[-–—~至到/])|约|大概|[-+–—~<>]|\b(?:about|around|roughly|approximately))\s*$", re.I)
COMBINED = re.compile(r"混在一起|拌在一起|一起称|mixed together|weighed together", re.I)
SEPARATOR = re.compile(r"、|\band\b|和|以及", re.I)
VAGUE = re.compile(r"^(?:还有|另外)?\s*(?:一些|少许|一点|some\s+|a little\s+)", re.I)
AMOUNT_PREFIX = re.compile(r"^\s*(?:还有|另外)?\s*(?:[一二两三四五六七八九十半\d]|half\b|one\b|two\b|some\b|一些|少许)", re.I)
STATE_PHRASES = (
    ("raw", r"还是生的|没煮|还没煮|未煮|没烹调|直接生吃(?:的)?|生吃(?:的)?|\bstill raw\b|\buncooked\b|\braw\b"),
    ("cooked", r"煮熟(?:了|以后)?|熟的|从锅里捞起来|\bstraight from the cooker\b|\bcooked\b"),
    ("dry", r"干货|\bdry\b"),
    ("roasted", r"\boven[- ]roasted\b|\broasted\b|清烤"),
    ("stewed", r"清炖(?:好了)?|\bstewed\b"),
)
STATE_SUFFIXES = tuple((state, re.compile(rf"(?:[\s,，;；]+|(?<=[\u3400-\u9fff]))({pattern})\s*$", re.I))
                       for state, pattern in STATE_PHRASES)
NON_CONSUMED_LEAD = re.compile(
    r"^(?:(?:我)?买了|炒了|下锅用了)\s*|^(?:i\s+)?(?:served|bought|purchased)\s+", re.I,
)
UNUSED_SUFFIX = re.compile(
    r"[,，;； ]*(?:但锅里(?:还)?剩[^，;；。]*|只吃了(?:一部分|部分|一些|一点)|"
    r"(?:今天)?(?:吃了|吃掉)一半)\s*$", re.I,
)
DISCOURSE_PREFIX = re.compile(r"^(?:分装的|称过的|\b(?:leftover|plain|room-temperature)\s+)", re.I)
MEASURE_TRAILER = re.compile(r"[,，]\s*(?:after (?:roasting|stewing|cooking)|before cooking)\s*$", re.I)
# Combine only explicit meat-only and skin/bone evidence, never a generic cut by itself.
SKINLESS_BREAST = re.compile(
    r"(?:鸡胸(?:净|纯)肉[,， ]*(?:去骨去皮|去皮去骨)|skinless chicken breast meat only)", re.I,
)
WEIGHING = (
    ("raw", re.compile(r"生重|称(?:的)?生重|\b(?:weighed raw|raw weight|before cooking)\b", re.I)),
    ("dry", re.compile(r"干重|\bdry weight\b", re.I)),
    ("cooked", re.compile(r"熟重|\b(?:weighed cooked|cooked weight|after (?:roasting|stewing|cooking))\b", re.I)),
)
PHRASE_END = re.compile(
    r"\s*(?:吃掉了|吃下了|还没称|没称|(?:直接)?按可食部分称重|[,，]\s*(?:an unknown amount|weighed))\s*$", re.I,
)
DANGLING_SCALE = re.compile(r"(?:^|[,，]\s*|\s+)(?:称了|称重|weighed)\s*$", re.I)
INCOMPLETE_AMOUNT = re.compile(r"[0-9０-９]")
HALF_CONSUMED = re.compile(r"(?:吃了|吃掉)(一半)")
TRIM = " \t\r\n，,;；。.!！"


def _span(original: str, start: int, end: int) -> SourceSpan:
    return SourceSpan(start=start, end=end, text=original[start:end])


def _segments(text: str):
    """Split only when a conjunction introduces an independently quantified mention."""
    start = 0
    if not LEAD.match(text.lstrip()):
        yield start, len(text)
        return
    for mark in SEPARATOR.finditer(text):
        if AMOUNT_PREFIX.match(text[mark.end():]) and OBSERVATION.search(text[start:mark.start()]):
            yield start, mark.start()
            start = mark.end()
    yield start, len(text)


def _amount_context(text: str, consumed: bool, issue: PortionIssue | None) -> AmountContext:
    if issue == "purchased_or_prepared":
        return "purchased" if re.search(r"买|购|\bbought\b|\bpurchased\b", text, re.I) else "prepared"
    if issue == "remaining_or_discarded":
        if re.search(r"丢|倒掉|\bdiscarded\b|\bthrew away\b", text, re.I):
            return "discarded"
        # An amount in the pan describes cooking input even if the sentence mentions leftovers.
        return "cooking_input" if re.search(r"锅|\b(?:pan|skillet|wok)\b", text, re.I) else "leftover"
    if issue == "cooking_input" or re.search(r"炒了[^，。]*油", text):
        return "cooking_input"
    if issue in ("partial_consumption", "consumed_amount_unknown"):
        return "unknown"
    if re.search(r"上桌|盛了|\bserved\b", text, re.I):
        return "served"
    if consumed:
        return "consumed"
    if re.search(r"煮了|做了|\bcooked\s+\d", text, re.I):
        return "cooked"
    return "unknown"


def _mention(text: str, start: int, end: int, inherited_consumption: bool) -> FoodMention:
    source = _span(text, start, end)
    phrase = source.text
    lead = LEAD.match(phrase.lstrip())
    cooked_after_dry = bool(re.search(r"(?:干[^，。]{0,24}煮熟|\bdry\b[^.]{0,32}\bthen cooked\b)", phrase, re.I))
    issue = portion_context_issue(phrase)
    if cooked_after_dry:
        issue = "measurement_state_unclear"
    consumed = inherited_consumption or bool(EATEN.search(phrase))
    markers = [(state, m) for state, pattern in WEIGHING if (m := pattern.search(phrase))]
    weighing = markers[0][0] if len(markers) == 1 else "dry" if cooked_after_dry and not markers else None
    prep_spans = [_span(text, start + m.start(), start + m.end()) for _, m in markers]
    matches = list(OBSERVATION.finditer(phrase))
    context = "prepared" if cooked_after_dry else _amount_context(phrase, consumed, issue)
    if issue is None and context == "cooking_input":
        issue = "cooking_input"
    observations = tuple(
        PortionObservation(
            quantity=_number(m["number"].casefold()), unit=m["unit"],
            span=_span(text, start + m.start(), start + m.end()),
            context=context, weighing_state=weighing,
            basis="includes_inedible" if issue == "edible_basis_unclear" else "stated_edible" if EDIBLE.search(phrase) else "unknown",
        )
        for m in matches
    )

    fraction = HALF_CONSUMED.search(phrase) if not observations else None
    if fraction:
        observations = (PortionObservation(quantity=Decimal("0.5"), unit="fraction_of_described_food",
                                           span=_span(text, start + fraction.start(1), start + fraction.end(1)),
                                           context="consumed"),)

    label = phrase.strip(TRIM)
    if lead:
        label = lead.string[lead.end():]
    label = VAGUE.sub("", label)
    if not lead:
        label = NON_CONSUMED_LEAD.sub("", label)
    label = DISCOURSE_PREFIX.sub("", label)
    uncertain_amount = len(matches) > 1 or any(
        RANGE.search(phrase[:m.start()]) or re.match(r"\s*[-–—~至到/]\s*\d", phrase[m.end():]) for m in matches
    )
    if len(matches) == 1:
        token = matches[0][0]
        # Only remove an amount at an expression boundary or after a weighing verb.
        label = re.sub(rf"^(?:称了\s*)?{re.escape(token)}\s*(?:of\s+)?", "", label, count=1)
        label = re.sub(rf"(?:称了\s*|吃了\s*|\s*){re.escape(token)}(?=$|[,，;；\s])", "", label, count=1)
    label = DANGLING_SCALE.sub("", PHRASE_END.sub("", label).strip(TRIM)).strip(TRIM)
    label = MEASURE_TRAILER.sub("", label).strip(TRIM)
    if issue or fraction:
        label = UNUSED_SUFFIX.sub("", label).strip(TRIM)
    preparation = None
    for state, pattern in STATE_SUFFIXES:
        suffix = pattern.search(label)
        if suffix and suffix.start() > 0:
            preparation = state
            raw_phrase = suffix[1]
            offset = phrase.casefold().rfind(raw_phrase.casefold())
            if offset >= 0:
                prep_spans.append(_span(text, start + offset, start + offset + len(raw_phrase)))
            label = label[:suffix.start()].strip(TRIM)
            break
    if SKINLESS_BREAST.fullmatch(label):
        label = "去皮去骨鸡胸肉" if label.startswith("鸡") else "skinless boneless chicken breast"
    if not preparation:
        prefix = re.match(r"(生|熟|干|raw\s+|cooked\s+|dry\s+)(?=鸡胸肉|米粉|米线|面条|chicken breast|rice noodles)", label, re.I)
        if prefix:
            preparation = {"生": "raw", "熟": "cooked", "干": "dry"}.get(prefix[1], prefix[1].strip().casefold())
            offset = phrase.find(label)
            if offset >= 0:
                prep_spans.append(_span(text, start + offset, start + offset + len(prefix[1])))
            label = label[prefix.end():].strip()
    if issue == "measurement_state_unclear" or (weighing and preparation and weighing != preparation
                                                and not (weighing == "cooked" and preparation in {"stewed", "roasted"})):
        weighing_conflict = True
    else:
        weighing_conflict = False
    checks = []
    if uncertain_amount or fraction or len(markers) > 1:
        checks.append("review_quantity")
    if issue or weighing_conflict:
        checks.append("review_portion_context")
    if label and (INCOMPLETE_AMOUNT.search(label) or len(label) > 120 or NON_ASSERTION.search(label)):
        checks.append("review_food_identity")
        label = ""
    if not label:
        checks.append("identify_food")
    return FoodMention(
        source=source, identity_expression=label or None, preparation=preparation,
        preparation_evidence=tuple(prep_spans), observations=observations,
        clarification=tuple(checks), portion_issue=issue or ("measurement_state_unclear" if weighing_conflict else None),
    )


def interpret_food_text(text: str) -> FoodInterpretation:
    if NO_INTAKE.fullmatch(text):
        return FoodInterpretation(original=text, status="no_consumption")
    if not text.strip() or len(text) > 2000 or NON_ASSERTION.search(text):
        return FoodInterpretation(
            original=text, status="review_required",
            mentions=(FoodMention(source=_span(text, 0, len(text)), identity_expression=None,
                                  clarification=("review_assertion",)),),
        )
    segments = tuple(_segments(text))
    # A purchase/discard/portion clause may refer to another span. Keep it together rather than
    # assuming each number belongs to a different consumed food.
    if portion_context_issue(text) or COMBINED.search(text) or len(segments) > 50:
        segments = ((0, len(text)),)
    consumed = bool(LEAD.match(text.lstrip()))
    mentions = tuple(_mention(text, start, end, consumed) for start, end in segments if text[start:end].strip(TRIM))
    status = "review_required" if not mentions or any(item.clarification for item in mentions) else "interpreted"
    return FoodInterpretation(original=text, status=status, mentions=mentions)


def preview_interpreted_food(text: str, normalizer: FoodNormalizer | None = None) -> FoodInterpretationPreview:
    interpretation = interpret_food_text(text)
    matcher = normalizer if normalizer is not None else get_food_normalizer()
    rows = []
    for mention in interpretation.mentions:
        observation = mention.observations[0] if len(mention.observations) == 1 else None
        review = bool(mention.clarification)
        quantity = unit = None
        is_mass = observation is not None and observation.unit.casefold() in MASS_FACTORS
        if observation and observation.quantity > 0 and math.isfinite(float(observation.quantity)):
            # State and weight are evaluated separately. Never place a gram observation into a
            # draft-ready FoodItem until a user confirms that mass via the existing workflow.
            if not review and not is_mass and observation.context in {"consumed", "unknown"}:
                quantity, unit = float(observation.quantity), observation.unit
        proposal = match = None
        if mention.identity_expression:
            proposal = FoodItem(name=mention.identity_expression, preparation_method=mention.preparation,
                                quantity=quantity, unit=unit)
            match = matcher.match_item(proposal)
        if review or (observation and (is_mass or observation.quantity <= 0)):
            portion = "needs_review"
        elif quantity is not None:
            portion = match.portion_status if match else "conversion_unavailable"
        else:
            portion = "quantity_unknown"
        rows.append(InterpretedMatch(mention=mention, proposal=proposal, reference_match=match, portion_status=portion))
    return FoodInterpretationPreview(interpretation=interpretation, items=tuple(rows))
