import json
from decimal import Decimal

import pytest

from app.schemas.food_logs import FoodItem
from app.services.food_normalization import ALIAS_PATH, FoodNormalizer


@pytest.fixture(scope="module")
def normalizer():
    return FoodNormalizer()


@pytest.mark.parametrize(
    ("phrase", "status", "reference", "portion"),
    [
        ("150g chicken breast", "food_state_unknown", None, "needs_review"),
        ("raw skinless boneless chicken breast, 150 g", "matched", "chicken_breast_skinless_boneless_raw", "edible_mass"),
        ("去皮去骨烤鸡胸肉 150g", "matched", "chicken_breast_meat_roasted", "edible_mass"),
        ("half a bowl cooked long-grain brown rice", "matched", "brown_rice_long_grain_cooked", "conversion_unavailable"),
        ("半碗糙米饭", "ambiguous_identity", None, "conversion_unavailable"),
        ("boiled egg", "ambiguous_identity", None, "quantity_unknown"),
        ("全熟去壳水煮蛋", "matched", "whole_egg_hard_boiled", "quantity_unknown"),
        ("一盘青菜", "ambiguous_identity", None, "conversion_unavailable"),
        ("豆腐 100g", "ambiguous_identity", None, "edible_mass"),
        ("海南鸡饭一份", "unsupported_food", None, "conversion_unavailable"),
        ("Latte", "unsupported_food", None, "quantity_unknown"),
        ("  80Ｇ，生西蘭花。 ", "matched", "broccoli_raw", "edible_mass"),
        ("canola oil in the pan, 15g", "matched", "canola_oil_as_sold", "quantity_unknown"),
        ("烤鸡胸肉（仅肉），150 g，生重", "food_state_unknown", None, "needs_review"),
        ("三杯鸡", "unsupported_food", None, "quantity_unknown"),
    ],
)
def test_identity_and_portion_are_separate(normalizer, phrase, status, reference, portion):
    result = normalizer.match_text(phrase)
    assert result.original == phrase
    assert result.identity_status == status
    assert result.portion_status == portion
    if reference:
        food = normalizer.foods[reference]
        assert result.reference.food_id == reference
        assert result.reference.fdc_id == food.source.fdc_id
        assert result.reference.source_url == food.source.url
        assert result.reference_version == normalizer.reference.reference_version
        assert result.matched_alias and result.matched_rule
    else:
        assert result.reference is None
    if status == "unsupported_food":
        assert not result.candidates


def test_shared_structured_matching_and_uncertain_image(normalizer):
    item = FoodItem(name="skinless boneless chicken breast", preparation_method="stewed", quantity=100, unit="g")
    manual = normalizer.match_item(item)
    text = normalizer.match_text("skinless boneless chicken breast, stewed, 100 g")
    assert manual.reference == text.reference
    assert manual.quantity == text.quantity == Decimal(100)
    assert manual.unit == text.unit == "g"
    uncertain = normalizer.match_item(item, identity_uncertain=True)
    assert uncertain.reference is None
    assert uncertain.candidates == (manual.reference,)
    assert uncertain.clarification == "confirm_identity"


def test_typo_is_nonbinding(normalizer):
    result = normalizer.match_text("raw brocoli 100g")
    assert result.identity_status == "ambiguous_identity"
    assert result.reference is None
    assert [candidate.food_id for candidate in result.candidates] == ["broccoli_raw"]


def test_explicit_verified_serving_and_unknown_sizes(normalizer):
    verified = normalizer.match_text("一个美标大号全熟去壳水煮蛋")
    assert verified.quantity == Decimal(1)
    assert verified.unit == "个"
    assert verified.portion_status == "verified_conversion"
    food = normalizer.foods[verified.reference.food_id]
    assert verified.portion_source_row_id in {row.source_row_id for row in food.portions}
    generic = normalizer.match_text("一个全熟去壳水煮蛋")
    assert generic.reference == verified.reference
    assert generic.portion_status == "conversion_unavailable"
    assert generic.portion_source_row_id is None


@pytest.mark.parametrize("portion", ["10–20g", "0g", "-10g", "about 20g", "1/2 cup", "one and a half cups", "10g 20g"])
def test_unclear_portions_never_resolve_to_verified_mass(normalizer, portion):
    result = normalizer.match_text(f"raw pak choi {portion}")
    assert result.portion_status not in {"edible_mass", "verified_conversion"}


def test_invalid_alias_index_rejected(tmp_path):
    index = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "aliases.json"
    index["exact_aliases"]["unknown_id"] = ["not a real food"]
    path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown food ID"):
        FoodNormalizer(alias_path=path)


def test_verified_size_does_not_convert_volume(normalizer):
    result = normalizer.match_text("一碗美标大号全熟去壳水煮蛋")
    assert result.reference.food_id == "whole_egg_hard_boiled"
    assert result.portion_status == "conversion_unavailable"
    assert result.portion_source_row_id is None


@pytest.mark.parametrize(
    ("name", "unit", "status", "portion"),
    [
        ("USDA medium peeled banana, length meets USDA standard", "piece", "matched", "verified_conversion"),
        ("去皮生香蕉", "根", "matched", "conversion_unavailable"),
        ("banana", "piece", "ambiguous_identity", "conversion_unavailable"),
        ("small raw peeled banana", "piece", "insufficient_information", "conversion_unavailable"),
        ("raw peeled banana, size unknown", "piece", "matched", "conversion_unavailable"),
        ("USDA medium peeled banana, length meets USDA standard", "cup", "matched", "conversion_unavailable"),
    ],
)
def test_banana_serving_requires_applicable_size_and_unit(normalizer, name, unit, status, portion):
    result = normalizer.match_item(FoodItem(name=name, quantity=1, unit=unit))
    assert result.identity_status == status
    assert result.portion_status == portion
    assert (result.portion_source_row_id == 93515) == (portion == "verified_conversion")
    assert result.original == name


def test_explicit_banana_specification_cannot_override_cooked_evidence(normalizer):
    result = normalizer.match_item(FoodItem(
        name="USDA medium peeled banana, length meets USDA standard",
        preparation_method="cooked", quantity=1, unit="piece",
    ))
    assert result.identity_status == "food_state_unknown"
    assert result.reference is None and result.portion_source_row_id is None


def test_structured_pan_quantity_still_requires_review(normalizer):
    result = normalizer.match_item(FoodItem(name="canola oil in the pan", quantity=15, unit="g"))
    assert result.quantity == Decimal(15)
    assert result.portion_status == "needs_review"
