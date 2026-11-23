"""Run the frozen synthetic holdout against the current deterministic text matcher."""

import csv
import hashlib
import io
from collections import Counter
from pathlib import Path

from app.services.food_normalization import FoodNormalizer
from scripts.evaluate_food_normalization import IDENTITY, PORTION

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "evaluation" / "food-normalization-holdout-v1.psv"


def load_cases(known_ids: set[str]) -> list[dict[str, str]]:
    payload = GOLD.read_bytes()
    checksum = GOLD.with_suffix(".sha256").read_text(encoding="utf-8").split()[0]
    if hashlib.sha256(payload).hexdigest() != checksum:
        raise ValueError("Frozen gold checksum does not match")
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8")), delimiter="|"))
    if [row["id"] for row in rows] != [f"{n:02d}" for n in range(1, 81)]:
        raise ValueError("Expected 80 ordered cases")
    if len({row["input"] for row in rows}) != len(rows):
        raise ValueError("Duplicate holdout expression")
    for row in rows:
        ids = set(filter(None, row["references"].split(",")))
        identity = row["identity"]
        clarification = {"M": "none", "C": "required", "G": "none", "U": "identify"}
        if (
            identity not in clarification or row["clarification"] != clarification[identity]
            or row["portion"] not in PORTION.values() or not ids <= known_ids
            or (identity == "M" and len(ids) != 1) or (identity in "GU" and ids)
            or None in row or not row["reason"] or not row["category"]
        ):
            raise ValueError(f"Invalid gold row {row['id']}")
    return rows


def main() -> None:
    matcher = FoodNormalizer()
    rows = load_cases(set(matcher.foods))
    counts = Counter()
    categories: dict[str, Counter] = {}
    for row in rows:
        result = matcher.match_text(row["input"])
        gold = row["identity"]
        actual = IDENTITY[result.identity_status]
        reference = result.reference.food_id if result.reference else ""
        portion = PORTION[result.portion_status]
        ids = set(filter(None, row["references"].split(",")))
        options = {candidate.food_id for candidate in result.candidates}
        correct = actual == gold and (actual != "M" or reference in ids)
        wrong_auto = actual == "M" and not correct
        wrong_portion = portion != row["portion"]
        unsafe_portion = (
            portion in {"E", "V"} and (row["portion"] in {"Q", "X", "R"} or portion == "V" and wrong_portion)
        )
        unjustified_options = options - ids if gold == "C" else options if gold in {"G", "U"} else options - ids
        if not correct or wrong_portion or unjustified_options:
            flags = ", ".join(label for active, label in (
                (wrong_auto, "unsafe automatic reference"),
                (unsafe_portion, "unsafe portion evidence"),
                (bool(unjustified_options), "candidate outside gold set"),
            ) if active)
            print(f"{row['id']} {row['input']} | expected {gold}/{row['references'] or '-'}/{row['portion']}"
                  f" | observed {actual}/{reference or '-'}/{portion}; candidates={','.join(sorted(options)) or '-'}"
                  f"{'; ' + flags if flags else ''}")
        metrics = {
            "cases": 1, "identity_correct": correct, "portion_correct": not wrong_portion,
            "gold_M": gold == "M", "correct_M": gold == "M" and correct, "actual_M": actual == "M",
            "wrong_auto": wrong_auto, "gold_CU": gold in "CU", "correct_CU": gold in "CU" and correct,
            "gold_C": gold == "C", "correct_C": gold == "C" and correct,
            "gold_U": gold == "U", "correct_U": gold == "U" and correct,
            "unnecessary_clarification": gold == "M" and actual == "C",
            "gold_G": gold == "G", "actual_G": actual == "G", "correct_G": gold == "G" and correct,
            "unsafe_portion": unsafe_portion, "unsafe_action": wrong_auto or unsafe_portion,
            "candidate_outside_gold": bool(unjustified_options),
            "gold_calculable_evidence": gold == "M" and row["portion"] in "EV",
            "correct_calculable_evidence": gold == "M" and row["portion"] in "EV" and correct and not wrong_portion,
        }
        counts.update(metrics)
        categories.setdefault(row["category"], Counter()).update(metrics)

    print("\nMetric | numerator/denominator")
    for name, numerator, denominator in (
        ("Correct automatic reference", "correct_M", "gold_M"),
        ("Incorrect automatic reference", "wrong_auto", "actual_M"),
        ("Correct ambiguity/abstention", "correct_CU", "gold_CU"),
        ("Correct clarification", "correct_C", "gold_C"),
        ("Correct unidentified", "correct_U", "gold_U"),
        ("Unnecessary identity clarification", "unnecessary_clarification", "gold_M"),
        ("Catalog gap precision", "correct_G", "actual_G"),
        ("Catalog gap recall", "correct_G", "gold_G"),
        ("Correct identity outcome", "identity_correct", "cases"),
        ("Correct portion outcome", "portion_correct", "cases"),
        ("Unsafe portion evidence", "unsafe_portion", "cases"),
        ("Unsafe automatic reference or portion evidence", "unsafe_action", "cases"),
        ("Candidate outside gold set", "candidate_outside_gold", "cases"),
        ("Correct reference plus calculable portion evidence", "correct_calculable_evidence", "gold_calculable_evidence"),
    ):
        print(f"{name} | {counts[numerator]}/{counts[denominator]}")
    print("\nCategory | identity | portion | exact ID / eligible | gap recall")
    for category, c in categories.items():
        print(f"{category} | {c['identity_correct']}/{c['cases']} | {c['portion_correct']}/{c['cases']}"
              f" | {c['correct_M']}/{c['gold_M']} | {c['correct_G']}/{c['gold_G']}")


if __name__ == "__main__":
    main()
