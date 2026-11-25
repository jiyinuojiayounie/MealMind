"""Export deterministic matching vocabulary for the browser calculator."""

import json

from app.services.nutrition_calculation import (
    KNOWN_MIXED_DISHES, MAX_EDIBLE_GRAMS, QUALIFIED_FOODS, UNSPECIFIED_STATE,
)
from app.services.nutrition_units import HOUSEHOLD_UNITS, MASS_FACTORS, PORTION_UNITS, PREPARATIONS, STATES


def browser_rules() -> dict:
    return {
        "mass_factors": {key: float(value) for key, value in MASS_FACTORS.items()},
        "household_units": sorted(HOUSEHOLD_UNITS),
        "portion_units": PORTION_UNITS,
        "preparations": PREPARATIONS,
        "states": sorted(STATES),
        "qualified_foods": QUALIFIED_FOODS,
        "unspecified_state": sorted(UNSPECIFIED_STATE),
        "mixed_dishes": sorted(KNOWN_MIXED_DISHES),
        "max_edible_grams": int(MAX_EDIBLE_GRAMS),
    }


if __name__ == "__main__":
    print(json.dumps(browser_rules(), ensure_ascii=False, indent=2, sort_keys=True))
