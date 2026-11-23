"""Offline comparison of existing recognition integration and deterministic text preview."""

import json
import re
from collections import Counter
from io import BytesIO
from unittest.mock import patch

from PIL import Image

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app
from app.schemas.food_interpretation import FoodInterpretationPreview
from app.schemas.food_logs import FoodItem
from app.schemas.food_recognition import FoodRecognitionRequest, QuotedFoods, VisibleFoods
from app.services.food_normalization import FoodNormalizer
from app.services.food_recognition import recognize_food_image, recognize_food_text
from app.services.nutrition_calculation import NutritionCalculator
from scripts.evaluate_food_normalization_holdout import IDENTITY, ROOT


def recognition_rows(case, settings, matcher):
    if case.get("photo_stub"):
        # Synthetic pixels exercise image plumbing only. The provider output is injected.
        image = BytesIO()
        Image.new("RGB", (8, 8)).save(image, format="PNG")
        fixture = VisibleFoods(items=case["visible"], needs_review=False)
        with patch("app.services.food_recognition.generate_structured", return_value=fixture):
            response = recognize_food_image(image.getvalue(), settings)
    else:
        keys = ("name", "evidence", "portion_text", "preparation_method")
        fixture = QuotedFoods(items=[dict(zip(keys, values, strict=True)) for values in case["provider"]],
                              needs_clarification=False)
        with patch("app.services.food_recognition.generate_structured", return_value=fixture):
            response = recognize_food_text(FoodRecognitionRequest(description=case["text"]), settings)
    for item in response.items:
        yield item, matcher.match_item(item, identity_uncertain=getattr(item, "identity_uncertain", False))


def interpreted_rows(case, client):
    response = client.post("/api/v1/food-normalization/interpret", json={"text": case["text"]})
    response.raise_for_status()
    for row in FoodInterpretationPreview.model_validate(response.json()).items:
        if row.proposal and row.reference_match:
            yield row.proposal, row.reference_match


def validate_cooking_input(case, rows, matcher, counts):
    """Test a quote-anchored validator rule offline. This is not installed in recognition."""
    text = case["text"]
    for (item, match), (_, quote, amount, _) in zip(rows, case["provider"], strict=True):
        start = text.find(quote)
        if amount and start >= 0 and text.count(quote) == 1 and quote.count(amount) == 1:
            amount_start = start + quote.index(amount)
            # A mass governed by a cooking-use verb is not the consumed mass.
            prefix = text[:amount_start]
            if re.search(r"(?:炒菜|做菜|烹饪)\s*用(?:了)?\s*$", prefix):
                counts["preserved_contextual_amount"] += 1
                print(f"C {case['id']} contextual evidence: {amount!r} "
                      f"at [{amount_start}, {amount_start + len(amount)}) as cooking_input")
                item = item.model_copy(update={"quantity": None, "unit": None, "portion_note": "portion_needs_review"})
                match = matcher.match_item(item)
        yield item, match


def score(case, rows, calculator, counts, mode):
    gold = case["gold"]
    counts.update(cases=1, expected_items=len(gold), empty_cases=not gold,
                  correct_empty=not gold and not rows, wrong_item_count=len(rows) != len(gold))
    for position, (name, prep, qty, unit, category, expected_id, review) in enumerate(gold):
        item, match = rows[position] if position < len(rows) else (None, None)
        reference = match.reference.food_id if match and match.reference else None
        status = IDENTITY[match.identity_status] if match else None
        quantity_correct = item is not None and (item.quantity, item.unit) == (qty, unit)
        unsafe_quantity = item is not None and qty is None and item.quantity is not None
        unsafe_reference = reference is not None and reference != expected_id
        # Review includes missing basis, ambiguity or an unavailable reference/portion.
        actual_review = item is not None and (status != "M" or match.requires_edible_weight_confirmation
                                             or match.portion_status != "verified_conversion")
        usable_without_binding = item is not None and calculator.calculate_item(
            FoodItem.model_validate(item.model_dump(include=set(FoodItem.model_fields))),
        ).status != "not_calculable"
        counts.update(
            name_correct=item is not None and item.name.casefold() == name.casefold(),
            prep_correct=item is not None and item.preparation_method == prep,
            quantity_correct=quantity_correct,
            unknown_expected=qty is None,
            unknown_correct=qty is None and quantity_correct,
            match_correct=(status, reference) == (category, expected_id),
            reference_eligible=expected_id is not None,
            reference_correct=expected_id is not None and reference == expected_id,
            review_correct=actual_review == review,
            unsafe_quantity=unsafe_quantity,
            unsafe_reference=unsafe_reference,
            legacy_calculable=usable_without_binding,
        )
        if not quantity_correct or (status, reference) != (category, expected_id) or not item or item.name.casefold() != name.casefold():
            print(f"{mode} {case['id']}.{position + 1}: expected {name}/{qty} {unit or '-'}/{category}/{expected_id or '-'}; "
                  f"observed {item.name if item else '-'}/{item.quantity if item else None} "
                  f"{item.unit if item else '-'}/{status or '-'}/{reference or '-'}")


def main():
    cases = json.loads((ROOT / "evaluation/food-workflow-diagnostic-v1.json").read_text(encoding="utf-8"))
    settings = Settings(_env_file=None, GEMINI_API_KEY="", environment="development")
    matcher = FoodNormalizer()
    calculator = NutritionCalculator(matcher.reference)
    totals = {mode: Counter() for mode in ("A/text", "B/text", "C/text", "A/photo")}
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)) as client:
        for case in cases:
            mode = "A/photo" if case.get("photo_stub") else "A/text"
            baseline = list(recognition_rows(case, settings, matcher))
            score(case, baseline, calculator, totals[mode], mode)
            if mode == "A/text":
                score(case, list(interpreted_rows(case, client)), calculator, totals["B/text"], "B/text")
                candidate = list(validate_cooking_input(case, baseline, matcher, totals["C/text"]))
                score(case, candidate, calculator, totals["C/text"], "C/text")
    print(f"C prototype newly marked contextual observations: {totals['C/text']['preserved_contextual_amount']}")
    for mode, c in totals.items():
        print(f"{mode} ({c['cases']} cases, {c['expected_items']} gold items)")
        for name, denominator in (
            ("name_correct", "expected_items"), ("prep_correct", "expected_items"),
            ("quantity_correct", "expected_items"), ("unknown_correct", "unknown_expected"),
            ("match_correct", "expected_items"), ("reference_correct", "reference_eligible"),
            ("review_correct", "expected_items"), ("unsafe_quantity", "expected_items"),
            ("unsafe_reference", "expected_items"), ("legacy_calculable", "expected_items"),
            ("correct_empty", "empty_cases"), ("wrong_item_count", "cases"),
        ):
            print(f"  {name}: {c[name]}/{c[denominator]}")


if __name__ == "__main__":
    main()
