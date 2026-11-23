# P0.3A input boundary and portion evidence

## What the evaluations measure

The frozen 80-case runner calls `FoodNormalizer.match_text` with one complete expression. This is an intentional raw-text probe of a narrow parser. It does not send a sentence to the structured `match_item` interface, and it does not simulate the application’s recognition step. The latter accepts a `FoodItem` with an independently supplied name, preparation, quantity and unit. The manual editor supplies these fields directly. Text recognition extracts quoted item and portion evidence and validates it before producing editable fields. Image recognition can supply a tentative food label and supported visible count. It cannot supply mass from pixels. Neither recognition route persists or confirms a log.

The identity layer should normalize the item label, honor preparation and measurement state, and retrieve only compatible verified USDA candidates. Portion evidence should travel independently, retaining stated observations while separating them from usable edible weight. Only draft review can confirm the reference and whether an entered mass represents edible weight in that state. The nutrition engine applies its existing weight or verified food-specific conversion rules to confirmed logs.

### Linked structured diagnostic

The 21-row [diagnostic fixture](food-normalization-structured-diagnostic-v1.psv) contains manually separated fields and interface-specific expected outcomes linked by holdout ID. These are synthetic editorial inputs, not measured Gemini outputs or estimates of end-to-end recognition accuracy. The subset is purposive. In case 50 the structured preparation field retains the contradictory context and the expected portion becomes review required. Case 33 probes an unrecognized everyday spelling independently from the raw-labeled state and portion.

From `backend/`, run `.venv/bin/python -m scripts.diagnose_food_normalization_inputs`.

| Interface on paired subset | Exact IDs / eligible | Identity outcomes | Portion outcomes before → after | Catalog gap recall |
|---|---:|---:|---:|---:|
| Raw expressions | 0/7 | 0/21 | 12/21 → 13/21 | 0/9 |
| Structured items | 5/6 | 8/21 | 19/21 → 21/21 | 0/9 |

Reference lookup succeeds when food name and state are separated for common rice, chicken, noodles and potato entries. The structured case for the reviewed hard-to-disambiguate tofu family can abstain correctly. The alternate broccoli spelling and ambiguity around boiled edamame still fail. None of the nine structured catalog gaps are labeled as gaps. This confirms genuine alias and catalog diagnosis weaknesses alongside the mismatch between a raw-language evaluation and the layer used in production.

## Portion failure diagnosis

| Frozen holdout case | Why it received an unsafe mass classification | P0.3A behavior |
|---|---|---|
| 14, blanched chicken | Positive mass was accepted even though the unmatched chicken entry did not establish an edible basis. | Review edible basis. |
| 16, skin-on roasted chicken | Preparation incompatible with the target meat-only basis was ignored by portion extraction. | Review edible basis. |
| 25, generic noodle | The unit and number passed without evidence of dry or cooked weighing. | Review measurement state. |
| 50, oil left in skillet | The context filter recognized a narrow pan phrase and missed skillet and leftover wording. | Review the consumed amount. Retain the stated 8 g separately. |
| 77, cooked potato of unknown preparation | The number survived the extraction and the forgotten preparation was ignored. | Review measurement state. |

Case 50 is frozen as quantity unknown. The new structured review result is deliberately more specific and remains a mismatch in the exact portion metric. Cases 14, 16, 25 and 77 depend on whether a score measures literal mass extraction or applicability to a compatible edible state. Case 16 explicitly states a consumed mass and includes skin. That can describe what was eaten while remaining incompatible with a meat-only reference. The older development case 25 identifies a more specific rice-noodle family and labels the stated mass separately from unresolved identity. The results preserve both original gold sets.

Known blocking contexts in English and Chinese now distinguish cooking input, purchased or prepared amounts, leftovers or discards, partial consumption, uncertain measurement state, and unclear edible basis. The raw response preserves a single parseable observation as `reported_quantity` and `reported_unit`. A contextual block withholds it as a recognized portion. Structured preview preserves the supplied fields and exposes a separate `portion_issue`. A known zero is reported as zero evidence with a review status rather than missing, and the existing positive-only logging contract still applies. No retained fraction, cooking loss or universal household conversion is inferred.

## Calculation reachability

The five raw holdout cases did not have a verified identity match and produced no calculations. The raw diagnostic entry point was not a persistence path. Bound nutrition separately requires a user-confirmed edible-weight flag for mass. For structured bound items, the portion review result also stops the calculation when contradictory context survives in the item. Neither the preview nor recognition can set the user's binding confirmation.

Before this change, text recognition could return a clean food name and positive gram quantity from a short quoted substring while dropping surrounding cooking-input context. If the user saved and confirmed that unbound item, the legacy estimator could calculate using the exact label and the recorded mass. A mocked recognition-to-draft-to-confirm-to-analysis regression now covers that path with canola oil. The corrected proposal keeps the original description, leaves the amount unknown, and confirmed analysis returns `quantity_unknown`.

The context checks are deliberately conservative within the quote's sentence. They can abstain when several foods or alternative weights share a sentence, and they do not fully resolve cross-sentence references or implied consumption. They do not reparse or rewrite historical logs, nor can they verify a separately entered manual value. Preserve measured and consumed evidence as separate typed fields in the next extraction iteration. Evaluate extraction against source spans, deterministic matching on verified structured inputs, and the combined workflow on a fresh independently reviewed corpus. Keep the frozen raw score as a separate baseline.

## Repeatable results

- Original 50 cases: exact ID 31/31, portion 50/50, unsafe automatic outcomes 0/50.
- Frozen 80 cases: exact ID 0/35, portion 51/80 → 53/80, unsafe portion evidence 5/80 → 0/80, and catalog gap recall 0/34. Automatic bindings remain zero. These results show evidence hardening rather than broader language coverage.
