# Nutrition analysis MVP design

Approved direction for Day 6. This design covers FR05–FR08 and the read side of the Plan → Log → Analyze → Replan loop. The reference snapshot, calculation engine, local daily API, and development-only Today card are implemented. [PRD](PRD.md) · [Decision record](DECISIONS.md)

## Current implementation and MVP scope

- Food logs store the original description, editable item names, optional positive quantities and free-text units, optional preparation methods, status, revision, and consumption timestamp with an offset. An `ai_text` or `ai_image` source describes how the log was started. It cannot establish how each item or portion was measured after editing. Recognition suggestions are separate from saved logs.
- SQLite indexes the recorded local consumption date and stores status separately from the JSON document. The existing list endpoint includes drafts. The proposed analysis read must add a dedicated confirmed-only lookup rather than relying on the browser to filter. The same local-development and loopback restrictions apply.
- Recipe catalog v3 already models ingredient IDs, preparation state, verified household portions, and provenance, but its 20 recipes are development drafts. Reuse compatible vocabulary and reviewed ID mappings where useful. Keep food composition records independent, and exclude draft recipes and generated meal plans from intake estimates.
- Today shows a read-only card for estimated kilocalories, protein, carbohydrate, and fat from confirmed records. Its date picker sends the local calendar date unchanged. Defer targets, historical charts, mixed-dish decomposition, and automated replanning.

### Approved invariants

Use only confirmed logs and group by the local calendar date in each stored timestamp's offset. Keep missing nutrient values, unknown amounts, and unresolved matches explicit. Trace every estimate to source records. Require compatible identity, preparation and state. Do not decompose mixed dishes into assumed ingredients or use Gemini to invent values or serving weights. Partial estimates must never appear as complete meal or day totals.

### Initial food coverage

Step 6.2A ships 30 traceable food-state records in the pinned USDA SR Legacy 2018-04 extract, with three exact, food-specific portion references. SR Legacy covers the selected forms in a single release and uses a consistent set of nutrient identifiers and definitions. Foundation Foods remains a research option for future coverage. Generic labels and unsupported preparations have no automatic fallback. [Snapshot and audit](../data/nutrition/README.md)

Initial categories include plain cooked white and brown rice, plain cooked noodles, dry oats, eggs, plain chicken breast, firm tofu, plain edamame, bok choy, broccoli, carrots, bananas, and measured cooking oil. Include raw and cooked variants only where an exact source row and a realistic logging case exist. Oil counts only if logged as consumed. A reported cooking-oil amount used in a whole pan does not establish an individual's intake.

Prioritize foods from fictional bilingual log examples and opt-in user feedback, without importing real private logs into fixtures. For very broad labels such as “青菜”, offer matching choices later. For ambiguous Chinese restaurant dishes, soups, sauces, or branded products without a matching reference, keep the original item and return an explanation and a next step. A measured ingredient can be logged separately only when the user knows it was consumed and it is not already part of a counted dish entry.

## Reference data and licensing

| Source | MVP decision |
| --- | --- |
| USDA FoodData Central | Primary source. Prefer matching Foundation Foods records where coverage and nutrient definitions align. Use SR Legacy for documented gaps. USDA publishes the data under CC0 and requests source attribution. FNDDS can inform later review of portion weights and prepared dishes, but US survey foods are unsuitable as default substitutes for local dishes. [Licensing](https://fdc.nal.usda.gov/) · [Data types](https://fdc.nal.usda.gov/data-documentation/) · [Versioned downloads](https://fdc.nal.usda.gov/download-datasets/) |
| Japan MEXT Standard Tables | Candidate for regional foods, especially tofu, vegetables, rice, and noodles when species, product type, and preparation match. Inspect the edition, footnotes, nutrient methods, and applicable asset terms before import. MEXT's special terms flag paid distribution as books or e-books. Check the terms of the exact asset and the proposed app or repository reuse before bundling an extract. Record attribution and any applicable notification or permission. [Official tables](https://www.mext.go.jp/a_menu/syokuhinseibun/mext_01110.html) · [Usage policy](https://www.mext.go.jp/b_menu/1351168.htm) · [Special terms](https://www.mext.go.jp/b_menu/1366610.htm) |
| China CDC / Chinese Nutrition Society food composition platform | Regional reference and a candidate for an authorized dataset. The access page identifies the institute as the data rightsholder. Keep public lookup separate from reuse approval. Obtain and record applicable reuse and redistribution rights before importing or bundling any rows. [Official platform notice](https://www.chinanutri.cn/yyzyxxpt/sjzx/swcfsjk/201911/t20191128_207183.html) |

The first curated and versioned snapshot lives under `data/nutrition/`. Use a JSON manifest and typed loader. Retain the provider, release identifier, stable provider food/record ID, individual nutrient source IDs and definitions, origin URL, retrieval date, units and edible basis, provenance notes, and license or permission evidence. Keep a review status for each food mapping and each portion factor. A documented match in one source is preferable to mixing nutrient values from different food definitions. Store the original nutrient codes and select a consistent carbohydrate definition and energy method across the first release. If a field uses a different definition or is flagged as missing/trace, preserve that distinction and leave it out of comparable estimates until reviewed. Source-defined zero stays zero.

No runtime data API, network lookup, credentials, or new storage service is needed. On every snapshot revision, review identity, cooked state, edible basis, nutrient metadata, licensing, and portion factors, then archive the prior version. Recalculation against a newer snapshot may change historical estimates. Return reference and algorithm versions on each API response.

## Calculation and uncertainty

1. **Identify the food.** Resolve the saved name to an exact reviewed bilingual alias or to a future user-selected canonical ID. Preserve the saved name. The match must establish relevant product variants and preparation state. For example, a reviewed alias for cooked rice can explicitly supply cooked state, while `鸡胸肉` alone may need raw/cooked clarification. Recognition is a suggestion. The calculation path never calls Gemini.
2. **Identify the consumed portion.** Use the quantity that the user confirmed in a log. Keep a missing amount as `null`. A confirmed photo-assisted log is eligible, but confirmation does not establish precision. In legacy logs, an item-level measurement method is unknown. A later logging iteration may add optional canonical food ID, measured state, edible/as-purchased basis, portion descriptor, and user-confirmed portion provenance. Until then, a calculation requires an unambiguous mapping from the existing name, preparation method, and unit.
3. **Convert to edible grams.** Convert positive mass units with fixed factors. A mass is usable only when its state and edible basis are clear, such as a reviewed plain cooked variant whose logged portion denotes the edible food. For inedible parts or ambiguous gross weights, require the edible amount or a reviewed matching yield factor and basis. Convert volume only with a matching density or evidence-backed portion weight for that food and state. Do not use raw reference rows for cooked weights or convert between them without a reviewed method and yield; defer general cooking-yield and nutrient-retention modeling.
4. **Apply reference nutrients.** For each available nutrient, calculate `edible_grams × value_per_100g ÷ 100`. Use source energy in kcal with a documented method and g for protein, carbohydrate, and fat. Decimal arithmetic and rounding rules must be deterministic. Sum unrounded item estimates before final display rounding. Keep null if a nutrient has no contributors. A missing component never becomes zero, and energy is not imputed from the other three fields in v1. Preserve trace and below-quantification status in reference metadata.
5. **Explain uncertainty.** Record whether the portion used a direct mass conversion or a reviewed portion factor. Numeric results are estimates even with measured portions. If the factor has a reviewed minimum and maximum and the quantity can be reconciled across that range, the response can carry those bounds as a scenario range. Otherwise omit bounds. The first UI should emphasize unknowns and documented typical portions rather than produce a range from unsupported guesswork. Never infer hidden oils or ingredients from a photo or a dish name.

| Household input | Rule |
| --- | --- |
| Bowl or cup | A personal bowl has no default capacity. Ask for a weighed edible portion or a reviewed named vessel/fill descriptor matched to that food. A standardized cup may be a known volume only when its standard is explicit. Volume does not imply mass without a matching factor. |
| Piece | Use a reviewed item and size, such as a specified egg size and edible basis. Unknown size stays unresolved if there is no reviewed matching descriptor; do not convert a generic piece count. |
| Serving | Resolve an exact labeled serving or reviewed dish and version with an edible gram weight. A generic serving stays unresolved. |
| Half bowl or handful | Preserve the fraction and original unit. Without an applicable factor or user-confirmed edible grams, the amount does not yield an estimate. |

Use data-backed, food-specific checks to flag implausible amounts for review. Never cap a value silently. Return stable reason codes such as `unknown_quantity`, `ambiguous_food`, `unsupported_food`, `state_unknown`, `edible_basis_unknown`, `conversion_unavailable`, `portion_needs_review`, and `reference_nutrient_missing`. Multiple reasons may apply to one item. Matching food and knowing its weight are independent.

## Implemented calculation boundary

`NutritionCalculator` loads the versioned local reference once per instance, or accepts an injected reference for offline tests. `calculate_item(FoodItem)` returns an `ItemNutritionResult`. `aggregate_nutrition(results)` returns per-nutrient subtotals and coverage for the items supplied to it. It has no date, persistence, or log status context. The future daily reader must select confirmed logs for the recorded date before passing their items to the engine.

- Matching uses the reference names and aliases with NFKC, case folding, and whitespace normalization. A small reviewed set of qualified food names, such as skinless boneless chicken breast, accepts exact preparation labels to select a variant. A generic cooked description can't choose between roasting and stewing. Conflicting or unsupported preparation information blocks the estimate even when the name matches. Known mixed dishes have a specific missing-data reason. Other unmatched names also fail closed without decomposition.
- Direct mass supports grams, kilograms and milligrams, including listed bilingual spellings. An explicit mass attached to a matched food is interpreted as edible weight for that reference. A quantity above 100 kg edible weight per item is withheld as a data-entry sanity check. This threshold does not assert typical or recommended portion sizes. The only count conversions are explicitly selected USDA large eggs or USDA medium raw banana, tied to the exact food ID and source portion row. Generic counts, bowls, cups and volume have no fallback.
- Each item reports `calculated`, `partial`, or `not_calculable`, with nullable estimates, edible weight, conversion kind, stable reason codes, and limitations. Matched items carry the food ID, its state, FDC ID/link, dataset version and release, and nutrient source row IDs. Converted counts also carry their portion source row ID.
- Arithmetic uses a fixed 50-significant-digit Decimal context with round-half-even for arithmetic precision. Existing float quantities enter as their shortest decimal representation. The calculation and aggregation apply no decimal-place rounding. A later presentation layer may round for readability. Summed values are nullable when no item contributes, and a sourced zero contributes normally.
- Implemented reasons are `ambiguous_food_match`, `food_not_found`, `food_state_unknown`, `food_preparation_mismatch`, `mixed_dish_unsupported`, `quantity_unknown`, `invalid_quantity`, `unsupported_unit`, `unsupported_serving_conversion`, `portion_needs_review`, and `nutrient_data_missing`. An aggregate with all supplied items calculated still reports `day_completeness: not_assessed`. The daily API maps the engine status `no_items` to `no_confirmed_logs`.

## Coverage and API contract

Use `GET /api/v1/nutrition/daily?date=YYYY-MM-DD`. Route and storage checks reuse the development-only food-log guard. A future public API must require owner isolation or be replaced by a separate private browser-local guest implementation. Do not send logs to a reference provider. Use the same `consumed_on` date as the Log screen, based on the offset recorded on each log. Do not use the UTC date, server's current timezone, or creation time.

Use a single read snapshot and filter `status = 'confirmed'` in the repository. Assert returned records are confirmed at the service boundary as defense in depth. Do not fetch planned meals, drafts, or recognition results. The endpoint uses the existing date index and opens a read-only SQLite connection. It does not create or migrate a database. An absent database is treated as having no confirmed logs. An unreadable, corrupt, or incompatible database returns a generic 503.

| Model | Proposed fields |
| --- | --- |
| `NutritionReference` | Canonical food ID, bilingual aliases, state, exact food definition, edible basis, nullable per-100-g values keyed by nutrient, source IDs and provenance, review metadata. |
| `PortionReference` | Food/state ID, normalized unit, size/fill descriptor, edible gram factor or documented range, evidence, release version, review status. |
| `ItemAnalysis` | Log ID, revision and 0-based item index, display name, resolved reference and portion IDs, nullable edible grams, conversion kind, per-nutrient estimates, reason codes. Original descriptions and photos stay out of this response. |
| `DailyNutritionAnalysis` | Requested date and `date_basis: recorded_offset`, required `reference_version` and `calculation_version`, confirmed log count, confirmed item count, count with all four values, coverage status, day completeness, per-nutrient totals, item analyses and referenced source metadata. |
| `NutrientSummary` | Unit, nullable `subtotal`, contributing item count, and missing item count. Optional reviewed bounds are separate from the subtotal; v1 need not return bounds. |

The daily response includes a top-level summary and one entry per confirmed log. Each entry includes its original ID, revision, meal type and offset-bearing timestamp, its own summary, and its indexed items. `review_guidance` maps the reason codes present in the response to short explanations. Decimal estimates are serialized as JSON strings and missing values as null.

Each subtotal describes the calculated subset of confirmed items and carries its own coverage denominator. Item-level coverage measures only how many confirmed items can be estimated. It does not estimate how much of the day's actual intake was recorded.

| API coverage status | Interpretation and UI label |
| --- | --- |
| `no_confirmed_logs` | No confirmed records for the date. Show an empty state and a Log link. All subtotals are null. |
| `not_calculable` | Confirmed items exist but none contribute to any of the four nutrients. Show reasons and leave subtotals null. |
| `partial` | At least one nutrient has a contributor, and some confirmed items or nutrients remain unresolved. Use “Partial estimate” and show contributors per nutrient as needed. |
| `all_logged_items_calculated` | Every confirmed item contributes to each nutrient. Use “Estimate for confirmed logs”. |
| `day_completeness: not_assessed` | Applies to every v1 response. Counting breakfast, lunch, and dinner cannot establish that snacks, drinks, or other intake were recorded. A separate future user attestation would be needed to describe a reported complete day, and estimates would still carry uncovered nutrient warnings. |

A valid date with no data or unsupported items returns HTTP 200 with the corresponding coverage status. Invalid date input returns 422. Unavailable development access follows the current 403/404 boundary. Database errors or failed reference integrity checks return a generic 503 with a stable error code. A successful response never substitutes zeros for missing values. Keep responses private with `Cache-Control: no-store`. Diagnostics should exclude raw log fields.

## UI, testing, and implementation order

- The bilingual Today card shows values and adjacent coverage counts such as “3 of 5 food items estimated”. It labels unavailable nutrients and displays nutrient-level coverage when it differs from full coverage. Expand each confirmed log to see the item details, translated missing-data reasons, and reference links. Loading, empty, unavailable and malformed responses have separate messages. No targets, clinical interpretation, or compensatory guidance.
- Do not offer an edit control on confirmed logs through the existing draft correction API. A future explicit correction flow needs separate product review, including historical records and how affected summaries change. See the [product backlog](PRODUCT_BACKLOG.md) for the collapsible per-item editor improvement.
- Reference tests should check numeric units, source IDs, known/missing/trace values, true zero, duplicate aliases, wrong raw/cooked mappings, and missing provenance or permission. Check that a reviewed serving factor cannot be used for a different food, state, container, or unit.
- Calculation fixtures should use clearly synthetic reference values for hand-checkable results. Cover known mass scaling, fractional reviewed portions, unknown amounts and units, ambiguous food and state, unsupported mixed dishes, measured cooking oil, per-nutrient partial coverage, preservation of nulls, and final-rounding sums. Verify no false zero or complete-day claim.
- API tests should cover draft exclusion, confirmed-only selection on repeat confirmation, no accidental persistence, same-date mixed offsets near midnight, missing data and storage errors, local access, and versioned deterministic responses. UI tests should cover bilingual mobile states, especially partial totals, unknowns, and provenance. Audit a small bilingual coverage fixture set before launch and revise the catalog based on observed gaps.

Implementation sequence after review:

1. Complete the approved scope and source policy. Step 6.2A curates the first reference snapshot and compares all imported values with the official release archive. Review regional food mapping and user-facing coverage wording before rollout.
2. Step 6.2B implements deterministic matching, edible-weight conversion, calculation, aggregation and fixture checks. Direct mass and the three specific USDA portions are supported.
3. Step 6.2C implements and verifies the confirmed-only reader and local daily endpoint, including local access, date semantics, provenance, and read-only behavior.
4. Step 6.3 adds the Today estimate card. Its local-development and loopback requirements match the food-log workflow. Replanning can consume this read model only after separate review of incomplete-data safeguards.
