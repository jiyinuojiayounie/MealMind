import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.schemas.food_logs import FoodItem
from app.schemas.food_normalization import (
    FoodAliasIndex, FoodCandidate, FoodNormalizationResult, FoodState, IdentityStatus, PortionIssue, PortionStatus,
)
from app.schemas.nutrition_reference import NutritionFood, NutritionReference
from app.services.nutrition_units import MASS_FACTORS, PORTION_UNITS, PREPARATIONS, STATES
from app.services.portion_evidence import portion_context_issue
from app.services.nutrition_reference import load_nutrition_reference

ALIAS_PATH = Path(__file__).resolve().parents[3] / "data" / "nutrition" / "food-aliases-v1.json"
NUMBERS = {"half": Decimal("0.5"), "半": Decimal("0.5"), "a": Decimal(1), "an": Decimal(1)}
NUMBERS.update({word: Decimal(index) for index, word in enumerate(
    ("one", "two", "three", "four", "five"), start=1,
)})
NUMBERS.update(dict(zip("一二三四五六七八九十两", map(Decimal, (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 2)), strict=True)))
UNITS = (
    *MASS_FACTORS, "ml", "毫升", "bowls", "bowl", "cups", "cup", "pieces", "piece", "servings", "serving",
    "handfuls", "handful", "plates", "plate", "个", "枚", "杯", "碗", "盘", "根", "份", "块", "片", "小把", "把",
)
PORTION_COUNT_UNITS = {
    "usda large egg": {"个", "枚", "piece", "pieces"},
    "usda medium banana": {"根", "个", "piece", "pieces"},
}
NUMBER = r"[0-9]+(?:\.[0-9]+)?" + "|" + "|".join(NUMBERS)
UNIT = "|".join(sorted(UNITS, key=len, reverse=True))
PORTION = re.compile(rf"(?<![\da-z.+/\-])(?P<number>{NUMBER})(?:\s+a\s+)?\s*(?P<unit>{UNIT})(?![a-z])", re.I)
QUALIFIER = re.compile(r"(?:^|[,;])\s*(生重|熟重|raw weight|cooked weight|stewed|roasted|raw|dry|cooked)\s*(?=$|[,;])", re.I)
MEASUREMENT = {**PREPARATIONS, "生重": "raw", "熟重": "cooked", "raw weight": "raw", "cooked weight": "cooked"}
UNKNOWN_AMOUNT = re.compile(r"\bamount eaten unknown\b|实际食用量未知|用量不详", re.I)
PAN_AMOUNT = re.compile(r"\bin the pan\b|下锅用量|锅中用量", re.I)
SIZE_NOTE = re.compile(r"[,;]?\s*(?:大小不详|size unknown)\s*$", re.I)
BANANA_DESCRIPTOR = re.compile(r"[,;]\s*(?:长度符合 usda|length meets usda standard)(?=[)]|$)", re.I)
# Generic staple labels do not establish whether the mass refers to dry or cooked food.
STATE_DEPENDENT_MASS_LABELS = {"noodle", "noodles", "pasta", "rice", "面条", "挂面", "大米"}
PEELED_BANANA_LABELS = {"香蕉 去皮", "去皮香蕉", "peeled banana", "banana without peel"}


def label_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[(),;、。!?]+", " ", value)
    value = re.sub(r"\bno salt\b", "without salt", value)
    return " ".join(value.split())


@dataclass(frozen=True)
class Evidence:
    label: str
    quantity: Decimal | None
    unit: str | None
    preparation: str | None
    portion_selector: str | None = None
    portion_needs_review: bool = False
    specification_rule: str | None = None
    portion_issue: PortionIssue | None = None
    reported_quantity: Decimal | None = None
    reported_unit: str | None = None


def _number(value: str) -> Decimal:
    return NUMBERS[value] if value in NUMBERS else Decimal(value)


def _read_evidence(text: str) -> Evidence:
    phrase = unicodedata.normalize("NFKC", text).casefold()
    issue = portion_context_issue(phrase)
    unknown_consumption = bool(UNKNOWN_AMOUNT.search(phrase) or PAN_AMOUNT.search(phrase))
    review = issue is not None and issue != "consumed_amount_unknown"
    portion_selector = None
    # These markers narrow the portion to an existing USDA row. They are not size estimates.
    if re.search(r"美标大号|\busda large\b", phrase):
        portion_selector = "usda large egg"
    if re.search(r"美标中等|\busda medium\b", phrase) and BANANA_DESCRIPTOR.search(phrase):
        portion_selector = "usda medium banana"
    sizes = r"美标大号|\busda large\b" if portion_selector == "usda large egg" else r"美标中等|\busda medium\b"
    if portion_selector:
        phrase = re.sub(sizes, "", phrase)
        phrase = BANANA_DESCRIPTOR.sub("", phrase)

    # Separate measurement/preparation qualifiers at punctuation boundaries, without deleting food-name qualifiers.
    preparation = None
    qualifiers = set()
    for segment in re.split(r"[,;]", phrase):
        match = QUALIFIER.fullmatch(segment.strip())
        if match:
            qualifiers.add(MEASUREMENT[match[1]])
    if qualifiers:
        preparation = next(iter(qualifiers)) if len(qualifiers) == 1 else "conflicting_state"
        phrase = QUALIFIER.sub("", phrase)

    matches = list(PORTION.finditer(phrase))
    if len(matches) == 1:
        match = matches[0]
        before, after = phrase[:match.start()].rstrip(), phrase[match.end():].lstrip()
        # Never turn a clipped range, approximate value, or pan input into a consumed mass.
        if re.search(r"(?:\d\s*[-–~至到/]|约|大约|\b(?:about|around|roughly|and)|[-–~])$", before) or re.match(
            r"[-–~至到/]\s*\d", after,
        ):
            return Evidence(text, None, None, preparation, portion_needs_review=True)
        phrase = phrase[:match.start()] + " " + phrase[match.end():]
        stated_quantity = _number(match["number"])
        stated_unit = match["unit"]
        quantity, unit = (None, None) if issue else (stated_quantity, stated_unit)
        # A measurement qualifier may be attached immediately before its amount.
        weight = re.search(r"(?:[,;]\s*|^)(生重|熟重|raw weight|cooked weight)\s*[,; ]*$", phrase)
        if weight:
            measured = MEASUREMENT[weight[1]]
            preparation = measured if preparation in (None, measured) else "conflicting_state"
            phrase = phrase[:weight.start()]
        if match["unit"] in MASS_FACTORS:
            phrase = re.sub(r"(?:[,;]\s*|\s+)edible\s*$", "", phrase)
    else:
        quantity = unit = stated_quantity = stated_unit = None
    if unknown_consumption:
        phrase = UNKNOWN_AMOUNT.sub("", PAN_AMOUNT.sub("", phrase))
    phrase = SIZE_NOTE.sub("", phrase)
    phrase = re.sub(r"(?:^some\s+|\s*(?:一些|少许)$)", "", phrase).strip(" ,;、。")
    # This USDA serving description specifies raw, peeled flesh. A generic size or
    # a bare peeled banana label alone does not establish this specification.
    specification_rule = None
    if portion_selector == "usda medium banana" and label_key(phrase) in PEELED_BANANA_LABELS:
        phrase = "raw peeled banana"
        specification_rule = "usda_medium_peeled_banana_specification"
    return Evidence(
        phrase, quantity, unit, preparation, portion_selector,
        review or (len(matches) > 1 and not unknown_consumption), specification_rule,
        issue, stated_quantity, stated_unit,
    )


def _one_typo(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1 or left == right:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right, strict=True)) == 1
    short, long = sorted((left, right), key=len)
    return any(short == long[:index] + long[index + 1:] for index in range(len(long)))


def _compatible(food: NutritionFood, preparation: str | None) -> bool:
    if preparation is None:
        return True
    if preparation in STATES:
        return food.state == preparation
    return food.state == "cooked" and bool(re.search(rf"\b{re.escape(preparation)}\b", food.preparation.casefold()))


class FoodNormalizer:
    def __init__(self, reference: NutritionReference | None = None, alias_path: Path = ALIAS_PATH):
        self.reference = reference if reference is not None else load_nutrition_reference()
        self.aliases = FoodAliasIndex.model_validate_json(alias_path.read_bytes())
        self.foods = {food.food_id: food for food in self.reference.foods}
        if self.aliases.reference_version != self.reference.reference_version:
            raise ValueError("Food aliases require a matching reference version")

        self.exact: dict[str, tuple[str, str]] = {}
        for food in self.foods.values():
            for label in (food.names.zh_cn, food.names.en_us, *food.aliases):
                self._add_exact(label, food.food_id, "reference_alias")
        for food_id, aliases in self.aliases.exact_aliases.items():
            self._check_ids((food_id,))
            for alias in aliases:
                self._add_exact(alias, food_id, "curated_alias")

        self.qualified = {label_key(label): variants for label, variants in self.aliases.qualified_aliases.items()}
        self.ambiguous = {}
        for group in self.aliases.ambiguous_aliases:
            self._check_ids(group.candidates)
            for label in group.labels:
                key = label_key(label)
                if key in self.ambiguous:
                    raise ValueError("Duplicate ambiguous food alias")
                self.ambiguous[key] = group
        if len(self.qualified) != len(self.aliases.qualified_aliases):
            raise ValueError("Duplicate qualified food alias")
        for variants in self.qualified.values():
            self._check_ids(tuple(variants.values()))
            if any(not _compatible(self.foods[food_id], method) for method, food_id in variants.items()):
                raise ValueError("Food alias has an incompatible preparation")
        self.unsupported = {label_key(label) for label in self.aliases.unsupported_labels}
        groups = [set(self.exact), set(self.qualified), set(self.ambiguous), self.unsupported]
        if len(set.union(*groups)) != sum(map(len, groups)):
            raise ValueError("Food alias policies overlap")
        self.unresolved = {label_key(label) for label in self.reference.unresolved_labels}
        if set(self.exact) & self.unresolved:
            raise ValueError("Exact food alias conflicts with an unresolved reference label")

    def _check_ids(self, ids: tuple[str, ...]) -> None:
        if any(food_id not in self.foods for food_id in ids):
            raise ValueError("Food alias references an unknown food ID")

    def _add_exact(self, alias: str, food_id: str, rule: str) -> None:
        key = label_key(alias)
        previous = self.exact.get(key)
        if not key or previous and previous[0] != food_id:
            raise ValueError("Conflicting exact food alias")
        if not previous:
            self.exact[key] = food_id, rule

    def _candidate(self, food_id: str) -> FoodCandidate:
        food = self.foods[food_id]
        return FoodCandidate(
            food_id=food_id, fdc_id=food.source.fdc_id, names=food.names,
            state=food.state, preparation=food.preparation, source_url=food.source.url,
        )

    def match_text(self, text: str) -> FoodNormalizationResult:
        # Start with whole-label recognition so a dish name such as 三杯鸡 is not parsed as a count.
        key = label_key(text)
        evidence = Evidence(text, None, None, None) if key in self.exact or key in self.unsupported else _read_evidence(text)
        return self._match(text, evidence)

    def match_item(self, item: FoodItem, *, identity_uncertain: bool = False) -> FoodNormalizationResult:
        return self._match(item.name, self._item_evidence(item), identity_uncertain=identity_uncertain)

    def portion_for_bound_item(self, item: FoodItem, food: NutritionFood) -> tuple[PortionStatus, int | None]:
        return self._portion(self._item_evidence(item), food.food_id, None)

    @staticmethod
    def _item_evidence(item: FoodItem) -> Evidence:
        unit = label_key(item.unit or "") or None
        preparation = label_key(item.preparation_method or "")
        label = _read_evidence(item.name)
        # The structured path can interpret qualifiers, but must not discard a
        # quantity embedded in a name or replace the item's recorded portion.
        issue = portion_context_issue(f"{item.name}; {item.preparation_method or ''}")
        amount_uncertain = issue is not None
        use_label = label.quantity is None and not label.portion_needs_review and not amount_uncertain
        selector = unit if unit in PORTION_UNITS else label.portion_selector if use_label else None
        method = MEASUREMENT.get(preparation, preparation) or None
        label_method = label.preparation if use_label else None
        if method and label_method and method != label_method:
            method = "conflicting_state"
        return Evidence(
            label.label if use_label else item.name,
            Decimal(str(item.quantity)) if item.quantity is not None else None,
            item.unit, method or label_method, selector,
            portion_needs_review=amount_uncertain and item.quantity is not None,
            specification_rule=label.specification_rule if use_label else None,
            portion_issue=issue, reported_quantity=label.reported_quantity, reported_unit=label.reported_unit,
        )

    def _identify(self, key: str, preparation: str | None):
        if not key:
            return "insufficient_information", None, None, (), "identify_food"
        if key in self.unsupported:
            return "unsupported_food", None, None, (), "reference_gap"
        if exact := self.exact.get(key):
            food_id, rule = exact
            if _compatible(self.foods[food_id], preparation):
                return "matched", food_id, rule, (), None
            return "food_state_unknown", None, None, (), "conflicting_preparation"
        if variants := self.qualified.get(key):
            if preparation in variants:
                return "matched", variants[preparation], "qualified_alias", (), None
            candidates = tuple(food_id for food_id in variants.values() if _compatible(self.foods[food_id], preparation))
            return "food_state_unknown", None, None, candidates, "measurement_state"
        if group := self.ambiguous.get(key):
            candidates = tuple(food_id for food_id in group.candidates if _compatible(self.foods[food_id], preparation))
            status = "food_state_unknown" if group.reason == "state_and_edible_basis" else "ambiguous_identity"
            return status, None, None, candidates, group.reason
        if key in self.unresolved:
            return "ambiguous_identity", None, None, (), "food_and_state"
        # Lexical similarity can only return non-binding candidates.
        if len(key) >= 5 and key.isascii() and re.fullmatch(r"[a-z -]+", key):
            candidates = tuple(sorted({
                food_id for alias, (food_id, _) in self.exact.items()
                if alias.isascii() and _one_typo(key, alias) and _compatible(self.foods[food_id], preparation)
            }))[:5]
            if candidates:
                return "ambiguous_identity", None, None, candidates, "check_spelling"
        return "insufficient_information", None, None, (), "identify_food"

    def _match(self, original: str, evidence: Evidence, *, identity_uncertain: bool = False) -> FoodNormalizationResult:
        key = label_key(evidence.label)
        status, food_id, rule, candidates, clarification = self._identify(key, evidence.preparation)
        if identity_uncertain and food_id is not None:
            status, food_id, rule, candidates, clarification = "ambiguous_identity", None, None, (food_id,), "confirm_identity"
        portion_status, portion_id = self._portion(evidence, food_id, clarification)
        issue = evidence.portion_issue
        if portion_status == "edible_mass" and food_id is None and re.search(r"鸡胸|\bchicken breast\b", key):
            portion_status, issue = "needs_review", "edible_basis_unclear"
        if portion_status == "edible_mass" and food_id is None and key in STATE_DEPENDENT_MASS_LABELS:
            portion_status, issue = "needs_review", "measurement_state_unclear"
        if issue is None and portion_status == "needs_review":
            if evidence.quantity == 0:
                issue = "zero_amount"
            elif clarification == "conflicting_preparation":
                issue = "measurement_state_unclear"
        state = self.foods[food_id].state if food_id else _state(evidence.preparation)
        return FoodNormalizationResult(
            original=original, food_label=evidence.label, preparation=evidence.preparation, food_state=state,
            identity_status=status, reference=self._candidate(food_id) if food_id else None,
            matched_rule=(evidence.specification_rule or rule) if rule else None,
            matched_alias=key if rule else None, candidates=tuple(map(self._candidate, candidates)),
            clarification=clarification, quantity=evidence.quantity, unit=evidence.unit, portion_status=portion_status,
            portion_issue=issue, reported_quantity=evidence.reported_quantity, reported_unit=evidence.reported_unit,
            requires_edible_weight_confirmation=(
                issue is None and evidence.quantity is not None
                and evidence.quantity > 0 and label_key(evidence.unit or "") in MASS_FACTORS
            ),
            portion_source_row_id=portion_id, reference_version=self.reference.reference_version,
            source_release=self.reference.source.release, alias_version=self.aliases.version,
        )

    def _portion(self, evidence: Evidence, food_id: str | None, clarification: str | None) -> tuple[PortionStatus, int | None]:
        if evidence.portion_needs_review:
            return "needs_review", None
        if evidence.quantity is None:
            return "quantity_unknown", None
        if not evidence.quantity.is_finite() or evidence.quantity <= 0:
            return "needs_review", None
        if label_key(evidence.unit or "") in MASS_FACTORS:
            if clarification in ("state_and_edible_basis", "preparation_and_edible_basis", "conflicting_preparation"):
                return "needs_review", None
            return "edible_mass", None
        selector = evidence.portion_selector or ""
        unit = label_key(evidence.unit or "")
        if unit != selector and unit not in PORTION_COUNT_UNITS.get(selector, ()):
            return "conversion_unavailable", None
        row_id = PORTION_UNITS.get(selector, {}).get(food_id or "")
        if food_id and any(row.source_row_id == row_id for row in self.foods[food_id].portions):
            return "verified_conversion", row_id
        return "conversion_unavailable", None


def _state(preparation: str | None) -> FoodState | None:
    if preparation in ("raw", "dry", "as_sold", "cooked"):
        return preparation
    if preparation in ("boiled", "hard-boiled", "poached", "baked", "roasted", "stewed"):
        return "cooked"
    return None


@lru_cache(maxsize=1)
def get_food_normalizer() -> FoodNormalizer:
    return FoodNormalizer()
