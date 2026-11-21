# Deterministic meal composition evaluation

The [offline fixtures](meal_composition_v1.json) run in `backend/tests/test_meal_composition.py` against development catalog version 2. Run `.venv/bin/python -m pytest -q tests/test_meal_composition.py` from `backend/`. Each fixture opts into draft mode or checks the default production boundary.

| Metric | Observed |
| --- | --- |
| Expected outcomes | 12 of 12 |
| Feasible plans | 5 of 12 fixtures. The other seven deliberately exercise rejection or unavailable candidates. |
| Required role coverage | 5 of 5 returned slots with required roles, including 4 of 4 complete lunches or dinners |
| Repeated recipes and families | Zero each across the five returned plans |
| Repeated primary ingredients | Zero across returned plans. Only one feasible fixture spans multiple meals. |

These fixtures test filtering and composition. They do not estimate real-world success rates, nutritional adequacy, allergen safety, or the accuracy of draft cooking times.

## Engine behavior and limits

- Supply structured meal slots, canonical ingredient IDs and preparation states, and any reviewed dietary tags or allergen exclusions. Use a single slot or a full day with breakfast, lunch, dinner, and an optional snack. A slot may request a single dish or override the default roles. The engine does not extract natural-language intent. Supply unresolved constraints explicitly to hold the request until clarification.
- Strict availability checks identity and state, and separately requires an affirmative process-water flag for recipes that need it. Flexible mode permits additional consumable ingredients and assumes process water unless explicitly unavailable or excluded. All modes require declared starting ingredients, including cooked rice, to be present. Inventory quantities and equipment capability are outside this check.
- Combine only the dishes needed to cover roles and an optional requested recipe. Sum the catalog's elapsed times sequentially, including documented waiting. Draft estimates require review. The result contains recipe roles and time estimates rather than nutrition judgments.
- Disallow repeated recipe and family IDs. Rank the remaining combinations with a penalty of four points per repeated primary ingredient across meals, a reward of two per distinct method and composition, and an optional two-point penalty per recent family match. The scoring function also exposes recipe and family repeat counts and penalties for independent tests. Break ties by dish count, elapsed time, and stable recipe IDs.
- Missing slot candidates, unresolved constraints, or a full-day conflict yield a structured no-feasible result. Production eligibility requires reviewed records. Both retrieval modes use the same allergen-evidence checks. No recommendation-history store is present.
- The engine enumerates role-minimal combinations and full-day products for the small development corpus. Benchmark or prune the search with completeness checks before expanding the catalog. Confirm structured constraint extraction, quantities, equipment and timing semantics, and review evidence before live integration.

## Cooking effort ranking with catalog v3

The offline regression in `backend/tests/test_planning_intent.py` runs “帮我安排今天三餐，适合一个人做，简单省事” in explicit draft mode. The baseline uses the same intent, including the one-serving filter, with the convenience preference disabled. A separate ordinary full-day request verifies the baseline ranking.

| Metric | Diversity-first baseline | Convenience ranking |
| --- | ---: | ---: |
| Independently prepared dishes | 7 | 5 |
| Sum of estimated elapsed minutes | 123 | 85 |
| Distinct required ingredient IDs | 17 | 13 |
| Distinct declared starting-state prerequisites | 0 | 0 |
| Required role coverage | 8 of 8 | 8 of 8 |
| Repeated recipe IDs / family IDs | 0 / 0 | 0 / 0 |
| Repeated primary ingredient occurrences across meals | 0 | 2 |
| Distinct cooking methods | 7 | 5 |
| Cooking effort points | 258 | 184 |

The effort score is 12 × dishes + elapsed minutes + 3 × distinct ingredient IDs + 8 × distinct declared ingredient/state prerequisites. Ingredients are counted once across the plan, including seasonings and consumable water. Process water is tracked separately and does not contribute points. Prerequisites such as cooked rice add points even if available. The existing eligibility gate still requires them to be available.

For convenience requests, eligible plans are ranked by effort points minus existing diversity points. Ties favor fewer multi-dish meals, then the existing diversity, dish count, elapsed time, and stable recipe ID order. The three internal meal types are a single recipe covering all required roles, a protein main with a separate staple, and other multi-dish meals. A single requested dish without required roles has no complete-meal classification. The deterministic winner is used for a convenience request even when optional catalog personalization is enabled.

For the response explanation, the initial per-meal reference is at most two dishes, 30 estimated minutes, eight distinct ingredients, and no declared starting-state prerequisites. This reference only affects the explanation. The selected breakfast, lunch, and dinner take an estimated 31, 33, and 21 minutes respectively, so the response reports partial satisfaction. The score and reference are ranking heuristics based on draft data. Cookware count, total active work, cleanup, and nutritional adequacy are outside the evaluation.
