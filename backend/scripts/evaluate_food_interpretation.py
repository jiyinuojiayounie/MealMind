"""Report independent parsing, structured matching, and combined food preview scores."""

import json
from collections import Counter

from app.services.food_interpretation import preview_interpreted_food
from app.services.food_normalization import FoodNormalizer
from scripts.diagnose_food_normalization_inputs import main as diagnose_structured
from scripts.evaluate_food_normalization_holdout import IDENTITY, PORTION, ROOT, load_cases


def score_parsing(matcher: FoodNormalizer) -> None:
    rows = json.loads((ROOT / "evaluation/food-interpretation-diagnostic-v1.json").read_text(encoding="utf-8"))
    metrics = Counter()
    for row in rows:
        legacy = matcher.match_text(row["text"])
        previous = {
            "names": [legacy.food_label],
            "preparations": [legacy.preparation],
            "amounts": [[str(legacy.reported_quantity), legacy.reported_unit]] if legacy.reported_quantity is not None else [],
            "contexts": [],
            "status": "review_required" if legacy.portion_status == "needs_review" else "interpreted",
        }
        parsed = preview_interpreted_food(row["text"], matcher).interpretation
        observations = [amount for mention in parsed.mentions for amount in mention.observations]
        actual = {
            "names": [item.identity_expression for item in parsed.mentions],
            "preparations": [item.preparation for item in parsed.mentions],
            "amounts": [[str(item.quantity), item.unit] for item in observations],
            "contexts": [item.context for item in observations],
            "status": parsed.status,
        }
        for key, value in actual.items():
            metrics["legacy", key] += previous[key] == row[key]
            metrics["combined", key] += value == row[key]
            if value != row[key]:
                print(f"Parsing: {row['text']} | {key} expected {row[key]!r}, got {value!r}")
        if row["status"] != "interpreted":
            metrics["abstention", "cases"] += 1
            metrics["abstention", "legacy"] += previous["status"] == row["status"]
            metrics["abstention", "combined"] += actual["status"] == row["status"]
    for key in ("names", "preparations", "amounts", "contexts", "status"):
        print(f"Parsing {key}: legacy {metrics['legacy', key]}/{len(rows)}; new {metrics['combined', key]}/{len(rows)}")
    denominator = metrics["abstention", "cases"]
    print(f"Parsing abstention: legacy {metrics['abstention', 'legacy']}/{denominator}; "
          f"new {metrics['abstention', 'combined']}/{denominator}")


def score_pipeline(matcher: FoodNormalizer) -> None:
    counts = Counter()
    for case in load_cases(set(matcher.foods)):
        gold, portion = case["identity"], case["portion"]
        expected_id = case["references"] if gold == "M" else None
        old = matcher.match_text(case["input"])
        preview = preview_interpreted_food(case["input"], matcher)
        item = preview.items[0] if len(preview.items) == 1 else None
        match = item.reference_match if item else None
        for mode, reference, status in (
            ("legacy", old, old.portion_status),
            ("pipeline", match, item.portion_status if item else "needs_review"),
        ):
            actual = IDENTITY[reference.identity_status] if reference else "U"
            food_id = reference.reference.food_id if reference and reference.reference else None
            correct = actual == gold and food_id == expected_id
            observed_portion = PORTION[status]
            counts[mode, "identity"] += correct
            counts[mode, "eligible"] += gold == "M"
            counts[mode, "exact"] += gold == "M" and correct
            counts[mode, "clarified"] += gold in "CU" and correct
            counts[mode, "gaps"] += gold == "G" and correct
            counts[mode, "portions"] += observed_portion == portion
            counts[mode, "matched_portions"] += correct and actual == "M" and observed_portion in "EV" and observed_portion == portion
            counts[mode, "unsafe_matches"] += actual == "M" and not correct
            counts[mode, "unsafe_weights"] += observed_portion in "EV" and (
                portion in "QXR" or (observed_portion == "V" and portion != "V")
            )
            if mode == "pipeline" and (not correct or observed_portion != portion):
                print(f"Pipeline {case['id']}: expected {gold}/{expected_id or '-'}/{portion}; "
                      f"got {actual}/{food_id or '-'}/{observed_portion}")
        counts["shared", "cases"] += 1
        counts["shared", "gaps"] += gold == "G"
        counts["shared", "clarified"] += gold in "CU"
        counts["shared", "matched_portions"] += gold == "M" and portion in "EV"
    for mode in ("legacy", "pipeline"):
        total = counts["shared", "cases"]
        print(f"{mode}: identity {counts[mode, 'identity']}/{total}; "
              f"exact ID {counts[mode, 'exact']}/{counts[mode, 'eligible']}; "
              f"clarification/abstention {counts[mode, 'clarified']}/{counts['shared', 'clarified']}; "
              f"catalog gaps {counts[mode, 'gaps']}/{counts['shared', 'gaps']}; "
              f"portions {counts[mode, 'portions']}/{total}; "
              f"reference plus usable portion {counts[mode, 'matched_portions']}/{counts['shared', 'matched_portions']}; "
              f"unsafe IDs {counts[mode, 'unsafe_matches']}/{total}; unsafe weight claims {counts[mode, 'unsafe_weights']}/{total}")


if __name__ == "__main__":
    normalizer = FoodNormalizer()
    score_parsing(normalizer)
    diagnose_structured()
    score_pipeline(normalizer)
