"""Evaluate the deterministic matcher against the unchanged Markdown gold set."""

import re
from pathlib import Path

from app.services.food_normalization import FoodNormalizer

GOLD = Path(__file__).resolve().parents[2] / "evaluation" / "FOOD_NORMALIZATION_V1.md"
ROW = re.compile(r"^\| (\d{2}) \| (.*?) \| ([MCGU]) ([^|]+?) \| ([EVQXR])(?:, .*?)? \|$", re.M)
IDENTITY = dict(matched="M", ambiguous_identity="C", food_state_unknown="C",
                unsupported_food="G", insufficient_information="U")
PORTION = dict(edible_mass="E", verified_conversion="V", quantity_unknown="Q",
               conversion_unavailable="X", needs_review="R")
CATEGORIES = (
    ("rice/oats", 1, 10), ("chicken", 11, 16), ("eggs", 17, 22),
    ("noodles", 23, 27), ("vegetables/soy/starch", 28, 40),
    ("fruit", 41, 42), ("mixed dishes/beverages/unknown", 43, 49), ("oil", 50, 50),
)


def main() -> int:
    matcher = FoodNormalizer()
    rows = ROW.findall(GOLD.read_text(encoding="utf-8"))
    if [int(row[0]) for row in rows] != list(range(1, 51)):
        raise ValueError("Expected 50 sequential gold case IDs")

    decisions = []
    for case, phrase, expected, detail, portion in rows:
        expected_id = detail.split()[0] if expected == "M" else None
        if expected_id and expected_id not in matcher.foods:
            raise ValueError(f"Unknown gold reference ID in case {case}")
        result = matcher.match_text(phrase)
        observed = IDENTITY[result.identity_status]
        observed_id = result.reference.food_id if result.reference else None
        observed_portion = PORTION[result.portion_status]
        correct = observed == expected and observed_id == expected_id
        portion_correct = observed_portion == portion
        unsafe_portion = observed_portion in "EV" and not portion_correct
        decisions.append((int(case), expected, observed, correct, portion_correct, unsafe_portion))
        if not correct or not portion_correct:
            print(f"{case} {phrase}: expected {expected}/{detail}/{portion}; "
                  f"observed {observed}/{observed_id or result.clarification}/{observed_portion}")

    def ratio(name, numerator, denominator):
        count = sum(numerator(row) for row in decisions)
        total = sum(denominator(row) for row in decisions)
        print(f"{name}: {count}/{total}")

    ratio("Exact IDs among eligible gold M", lambda r: r[1] == "M" and r[3], lambda r: r[1] == "M")
    ratio("Incorrect automatic IDs", lambda r: r[2] == "M" and not r[3], lambda r: r[2] == "M")
    ratio("Correct ambiguity/unknown abstentions", lambda r: r[1] in "CU" and r[3], lambda r: r[1] in "CU")
    ratio("Unnecessary identity clarification", lambda r: r[1] == "M" and r[2] == "C", lambda r: r[1] == "M")
    ratio("Correct known catalog gaps", lambda r: r[1] == "G" and r[3], lambda r: r[1] == "G")
    ratio("Correct portion outcomes", lambda r: r[4], lambda r: True)
    ratio("Unsupported automatic portion outcomes", lambda r: r[5], lambda r: True)
    for name, first, last in CATEGORIES:
        subset = [r for r in decisions if first <= r[0] <= last]
        print(f"{name}: identity {sum(r[3] for r in subset)}/{len(subset)}, "
              f"portion {sum(r[4] for r in subset)}/{len(subset)}")
    return int(any((r[2] == "M" and not r[3]) or r[5] for r in decisions))


if __name__ == "__main__":
    raise SystemExit(main())
