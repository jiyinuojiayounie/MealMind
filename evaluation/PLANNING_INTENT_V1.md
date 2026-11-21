# Planning intent v1 evaluation

The [33 annotated fixtures](planning_intent_v1.json) exercise the closed-phrase extractor and the structured adapter against draft catalog version 2. Run `.venv/bin/python -m pytest -q tests/test_planning_intent.py` from `backend/`. The cases are authored examples and deliberate rejection cases. They do not estimate real-world language accuracy or catalog coverage.

| Measure | Observed |
| --- | --- |
| Annotated extraction | 53 of 53 individual field-value checks passed, plus exact explicit-field and issue-code checks on all 33 cases. |
| Outcomes | 12 successful plans, 5 no feasible plan, 13 clarification required, and 3 unsupported constraints. All 33 matched the annotated outcome. |
| Blocking ambiguous or unsupported inputs | 16 of 16. This includes safety statements held for confirmation and explicit flavor or whole-day time constraints the catalog or engine cannot validate. |
| Unsafe or silently dropped hard constraints | Zero observed across the 22 tagged hard-constraint fixtures. Success cases check exact ingredient IDs and states, process water, and elapsed-time limits as applicable. Others check the expected block or no-feasible result. This is fixture coverage only. |
| Full-day requests | Six recognized as full-day, of which three returned a plan. The conflicting full-day versus one-dish case is tracked separately as clarification. |
| Required meal-role coverage | 15 of 15 returned slots with required roles. This measures catalog labels. |
| Recipe diversity | Zero repeated recipe IDs and zero repeated family IDs across returned plans. Two repeated primary-ingredient occurrences across meals were counted. |

The backend suite also checks production mode and trusted safety confirmation. Confirming one clause does not clear another. A confirmed allergen exclusion can still return no feasible plan when catalog evidence is missing.

## Supported vocabulary and boundaries

- Recognizes whole clauses for dinner, other meal slots, one dish, explicit complete dinner, and full-day plans. Dinner and complete-meal defaults remain distinguishable in `explicit_fields`.
- Recognizes integer minute limits, a small bilingual ingredient/state alias table, and explicit strict lists such as “我只有鸡蛋和番茄”. Use “and” or “、” between ingredients. A bare full-day time limit needs clarification. An explicit whole-day time budget is unsupported.
- Recognizes Chinese home cooking as a soft cuisine preference. A mild flavor preference can be reported as unapplied. An explicit “not spicy” constraint blocks planning because there is no reviewed flavor metadata. Plain inventory declarations permit additions, while strict declarations remain hard limits.
- Preserve the original text exactly. Record wholly unrecognized clauses, ambiguous aliases, and conflicting fields. Candidate safety phrases are recorded for review. Keyword detection is neither an allergen mapping nor safety validation. Only a trusted future confirmation step can attest which statements are covered by structured restrictions. Candidate selection then requires catalog evidence.
- Free-form multi-clause syntax without clear separators, arbitrary ingredients or portion quantities, named recipe extraction, numeric budget or nutrition targets, and cooking-only or day-level time budgets are outside the prototype. Punctuation, aliases, negation, and mixed language must be evaluated beyond this small fixture set.
