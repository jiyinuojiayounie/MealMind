"""Compare linked raw samples with manually supplied structured items, without recognition calls."""

import csv
from collections import Counter

from app.schemas.food_logs import FoodItem
from app.services.food_normalization import FoodNormalizer
from scripts.evaluate_food_normalization_holdout import IDENTITY, PORTION, ROOT, load_cases

STRUCTURED = ROOT / "evaluation" / "food-normalization-structured-diagnostic-v1.psv"


def main() -> None:
    matcher = FoodNormalizer()
    originals = {row["id"]: row for row in load_cases(set(matcher.foods))}
    counts = Counter()
    with STRUCTURED.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="|"):
            original = originals[row["holdout_id"]]
            item = FoodItem(
                name=row["name"], preparation_method=row["preparation"] or None,
                quantity=float(row["quantity"]) if row["quantity"] else None, unit=row["unit"] or None,
            )
            counts["cases"] += 1
            # Score each interface against its own labels; structuring can change the evidence.
            for mode, expected, result in (
                ("raw", original, matcher.match_text(original["input"])),
                ("structured", row, matcher.match_item(item)),
            ):
                status, portion = IDENTITY[result.identity_status], PORTION[result.portion_status]
                food_id = result.reference.food_id if result.reference else ""
                exact = status == expected["identity"] and (
                    status != "M" or food_id == (expected.get("reference") or expected.get("references"))
                )
                counts[mode, "identity"] += exact
                counts[mode, "portion"] += portion == expected["portion"]
                counts[mode, "eligible"] += expected["identity"] == "M"
                counts[mode, "correct_id"] += exact and status == "M"
                counts[mode, "gap_eligible"] += expected["identity"] == "G"
                counts[mode, "gap_detected"] += exact and status == "G"
                if mode == "structured" and (not exact or portion != expected["portion"]):
                    print(f"{row['holdout_id']}: {item.name}; expected {expected['identity']}/{expected['portion']}, "
                          f"got {status}/{portion} ({food_id or '-'})")
    for mode in ("raw", "structured"):
        print(f"{mode}: identity {counts[mode, 'identity']}/{counts['cases']}; "
              f"exact ID {counts[mode, 'correct_id']}/{counts[mode, 'eligible']}; "
              f"portion {counts[mode, 'portion']}/{counts['cases']}; "
              f"catalog gaps {counts[mode, 'gap_detected']}/{counts[mode, 'gap_eligible']}")


if __name__ == "__main__":
    main()
