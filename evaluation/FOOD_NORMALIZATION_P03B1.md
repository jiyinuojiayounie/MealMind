# P0.3B-1 layered food interpretation evaluation

## Contract and integration

The development-only, no-store `POST /api/v1/food-normalization/interpret` accepts `{"text":"..."}` and returns the original text, interpretation status and one or more reviewed proposals. Each mention records the source range using zero-based Python character offsets with an exclusive end, a food expression, preparation and its source spans, amount observations with quantity and unit, the amount's context and weighing state where known, edible-basis evidence, and clarification codes. A single exact food, a separately quantified simple list, and an unresolved or negated statement are distinct cases. A mixed dish stays whole.

The deterministic parser uses shared quantity vocabulary and portion-safety rules, then projects a draft item through the existing `FoodItem` shape and calls `FoodNormalizer.match_item`. An observed mass stays in the evidence record, even when a statement says it was eaten. It is never added to the draft item by this route. A household quantity may be kept, with conversion status from the existing structured matcher. The normalization response is a candidate or a reference suggestion. Neither output confirms identity, edible weight, or consumption. The preview never opens the log database or calls a provider. It does not affect the current manual log, text/image recognition, binding validation, or Today routes. To use it in a later UI, review the source and preparation, collect edible-weight confirmation separately, then use the existing draft-to-confirm flow.

## Three layers

Run from `backend/` with the existing virtual environment.

```sh
.venv/bin/python -m scripts.evaluate_food_normalization
.venv/bin/python -m scripts.evaluate_food_normalization_holdout
.venv/bin/python -m scripts.evaluate_food_interpretation
```

The 16-case [parsing diagnostic](food-interpretation-diagnostic-v1.json) is a development fixture. Each field is an exact per-expression check over the full list of mentions or observations. The legacy baseline projects the fields available from the old raw interface. That interface has no typed amount context or explicit no-consumption status, so these comparisons describe capability as well as correctness. The two passing legacy context rows contain no expected amount contexts. The seven abstention cases require review or explicitly report no consumption.

| Parsing metric | Legacy | New |
|---|---:|---:|
| Identity expressions | 4/16 | 16/16 |
| Preparation fields | 12/16 | 16/16 |
| Observed quantity and unit | 14/16 | 16/16 |
| Amount context | 2/16 | 16/16 |
| Interpretation status | 10/16 | 16/16 |
| Correct abstention | 4/7 | 7/7 |

The separate 21-case [manually structured fixture](food-normalization-structured-diagnostic-v1.psv) continues to produce 5/6 correct eligible reference IDs, 8/21 correct overall identity outcomes, 21/21 correct portion statuses and 0/9 correct catalog-gap classifications. Manual shaping isolates the matcher. It supplies no evidence about model recognition performance.

The frozen 80-case dataset and SHA-256 are unchanged. These expressions and results were inspected during development, so the pipeline comparison is diagnostic regression evidence. Its role is to show the effect of parsing on an existing verified matcher. Reserve a fresh corpus, written and gold-reviewed independently of implementation, for a future generalization estimate. Include separate raw and structured inputs, multiple mentions, source-span adjudication, mixed dishes, negations, competing weights, ambiguous state, catalog gaps, and cases where a model must abstain. Freeze the gold and analysis plan before running the pipeline. Use model outputs only after explicit approval for a separate evaluation.

| Frozen 80-case metric | Legacy raw | Parse then structured match |
|---|---:|---:|
| Exact automatic reference on gold M cases | 0/35 | 4/35 |
| Correct overall identity | 4/80 | 7/80 |
| Correct clarification/abstention on gold C/U cases | 4/11 | 3/11 |
| Known catalog gap detection | 0/34 | 0/34 |
| Exact portion status | 53/80 | 33/80 |
| Correct reference and usable portion evidence | 0/21 | 0/21 |
| Incorrect automatic reference | 0/80 | 0/80 |
| Unsafe automatic weight evidence | 0/80 | 0/80 |

The pipeline metric uses the raw gold portion codes. Its stricter policy reports observed grams as review-needed, even where the gold E label would count the amount as usable evidence. This contributes to the reduced exact portion score and does not change the gold. Some informal household phrases, explicit serving specifications, and unknown-amount strings also remain unresolved. The safety counts cover only this fixture and do not prove unrestricted input safety. The original 50-case entry point remains at 31/31 exact ID, 50/50 portions, and zero unsafe outcomes.

## Remaining examples

- Cases 03–04 now use the cooker or uncooked phrase to resolve long-grain brown rice. Cases 11–12 resolve explicit skinless/boneless raw or roasted chicken evidence. Their reference IDs can be suggested while their weights remain outside the draft.
- Cases 01–02 still fail to join rice variety, fortification, preparation and chronology across clauses. Cases 08–09 similarly miss oats with fortification and preparation described separately. Cases 35 and 42 surface unresolved colloquial food terms. These are parsing or vocabulary gaps with potentially compatible records.
- Case 30 loses the legacy dry rice noodle typo clarification in the composed path. It safely abstains, reducing the C/U score by one. No spelling fallback may auto-bind a different food.
- Cases 17–18 miss distinctions among egg preparation descriptions. Cases 75–76 miss existing verified serving specifications expressed in free text. Explicit basis/size can be retained for later review. The parser does not convert their counts.
- Cases 20, 39, 44 and 61 represent real coverage gaps: steamed egg custard, soft tofu, steamed sweet potato and soy milk. They remain unresolved instead of being identified as known gaps in this run. Better parsing can improve diagnosis but cannot supply a missing verified record.
