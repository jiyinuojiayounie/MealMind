# Food normalization holdout v1

## Scope and reproducibility

The [frozen set](food-normalization-holdout-v1.psv) contains 80 synthetic single-food expressions in eight equally sized food categories, with Chinese, English and mixed-language examples. It deliberately stresses conversational clauses, informal quantity phrases, ambiguity, and catalog gaps. Labels were assigned against the pinned 30-record SR Legacy snapshot and portion contract before any holdout inference. The original 50 cases served as a separate baseline. The set overlaps with the development set in some underlying foods and policies. The same author inspected the system and authored the holdout, with no independent second review and no real-user sampling. Neither the case mix nor its measured error rates estimates production frequencies.

The gold file was frozen at SHA-256 `a980810ef8c54e038fefe7485cd0ca864fd1acfe6f6e4838e934373561e4c893`. The [checksum](food-normalization-holdout-v1.sha256) is checked before evaluation. From `backend/`, run `.venv/bin/python -m scripts.evaluate_food_normalization_holdout`. The runner uses the unchanged `FoodNormalizer.match_text` at implementation commit `9006ee6`. This measures standalone expression handling. The live structured preview also receives separately entered quantities, units and preparation details, which can change results. The run used no network, Gemini, SQLite or automatic conversion to nutrition values.

### Scoring

- Identity uses M for automatic match, C for clarification, G for a known catalog gap and U for insufficient identifying information. Either clarification status counts as C. A correct automatic match requires the exact frozen ID. The candidate column for C is an allow-list of options that could be appropriate after clarification. Offering fewer choices is allowed. Candidate availability is reported separately, and a candidate cannot itself count as an automatic match.
- Portion uses E for explicit applicable mass evidence, V for a verified food-specific serving specification, Q for unknown amount, X for unavailable conversion and R for evidence requiring review. Scores treat identity and portions independently. A matching food and an E/V status are an evidence-level proxy for possible calculation, subject to the regular weight basis and confirmation checks. This run never calculated daily nutrition.
- An incorrect automatic ID includes a wrong reference or an automatic binding where gold requires clarification, abstention or a catalog gap. Unsafe portion evidence is an E/V returned for Q/X/R, or an unsupported V. Candidate IDs outside the gold allow-list are separately flagged. The combined safety rate counts the union of unsafe reference and portion cases. Empty denominators are undefined.

## Results

| Metric | Result | Denominator |
|---|---:|---|
| Exact automatic reference | 0/35 | Gold M |
| Incorrect automatic reference | 0/0, undefined rate | Actual M; 0 such cases out of all 80 |
| Correct ambiguity or abstention | 4/11 | Gold C or U |
| Correct ambiguity handling | 1/8 | Gold C |
| Correct unidentified outcome | 3/3 | Gold U |
| Unnecessary identity clarification | 0/35 | Gold M returned C; all 35 instead returned U |
| Known catalog gap precision | 0/0, undefined | Actual G |
| Known catalog gap recall | 0/34 | Gold G |
| Correct identity outcome | 4/80 | All cases |
| Correct portion status | 51/80 | All cases |
| Unsafe portion evidence | 5/80 | All cases |
| Unsafe automatic reference or portion evidence | 5/80 | All cases |
| Out-of-set candidates | 0/80 | All cases |
| Correct ID and calculable portion evidence | 0/21 | Gold M with gold E or V |

There were 79 U and one C output. Case 30 supplied the only candidate list, containing the valid dry rice noodle reference; it already asks for confirmation. Of five gold C cases with an allowable candidate list, one received a list. No gold M received a shortlist. The original development baseline retained 31/31 exact automatic matches and 50/50 portion states.

| Category | Identity | Portion | Exact ID / eligible | Gap recall |
|---|---:|---:|---:|---:|
| Rice and grains | 0/10 | 7/10 | 0/6 | 0/3 |
| Meat and eggs | 0/10 | 5/10 | 0/5 | 0/4 |
| Noodles | 1/10 | 6/10 | 0/5 | 0/3 |
| Vegetables and soy | 0/10 | 7/10 | 0/6 | 0/2 |
| Roots, fruit and oil | 0/10 | 8/10 | 0/7 | 0/3 |
| Mixed dishes | 0/10 | 7/10 | — | 0/10 |
| Beverages and snacks | 0/10 | 6/10 | — | 0/9 |
| Uncertainty and portions | 3/10 | 5/10 | 0/6 | — |

## Failure modes and severity

- **A — Alias and normalization gaps.** Conversational context remains part of the lookup label. Case 11 states raw, boneless, skinless edible chicken and mass; only the mass survives as a recognized field. Case 42 states the regional potato name, peeled, plain-boiled and cooked mass. Cases 75–76 also expose missing syntax for explicit verified size specifications.
- **B — Meaningful ambiguity.** Cases 15, 37 and 40 lack required state or preparation details. A model may phrase a question, but input alone cannot establish the answer. Case 66 may mean a packaged wafer or an egg dish. A similar-sounding reference cannot resolve this.
- **C — Verified catalog coverage.** All 34 known gaps are reported as unidentified; this is a diagnosis miss on top of a real scope limitation. Mixed dishes, steamed or seasoned variants, beverages and snacks cannot use superficially similar rows.
- **D — Portion expression coverage.** In 21 cases, an expressed household count or measure labeled X was returned Q. These failures lose useful portion evidence, while both outcomes withhold conversion. Instances include bites, bags, spoonfuls and chopstick portions. Two V cases yielded Q. They are missed conversions, with no invented grams.
- **E — Disputable gold.** Case 35 uses a regional label that may not mean the same vegetable for all speakers. Case 73's trailing question mark could mean doubt about identity. Cases 14, 16, 25 and 77 use R to score mass suitability for a reference state or edible basis, while a policy that scores literal gram extraction alone could choose E. Case 16 in particular explicitly describes skin-on food and an eaten amount. These distinctions warrant independent label review before using the numbers as a release threshold. Frozen labels and counts remain unchanged.
- **F — Other defects.** Case 50 is the highest-priority safety defect. The text specifies oil in the skillet and some left behind, yet the evidence parser promotes 8 g to edible mass. It returned no reference, so this run produced no nutrient calculation. A later identity improvement could expose the erroneous mass. Cases 14, 16, 25 and 77 likewise promoted mass despite the frozen R requirement. Case 72's unsupported scientific notation was reported as unknown instead of being flagged for review.

### Case-level mismatches

Each row below shows frozen identity, ID or candidate set, and portion versus observed identity, bound ID, and portion. Compound codes indicate separate identity and portion problems. A dash denotes an empty reference field. Inputs and labelling reasons are in the frozen dataset.

| Case | Gold | Observed | Failure analysis |
|---|---|---|---|
| 01 | M/white_rice_long_grain_unenriched_cooked/E | U/-/E | A |
| 02 | M/white_rice_long_grain_unenriched_raw/E | U/-/E | A |
| 03 | M/brown_rice_long_grain_cooked/Q | U/-/Q | A |
| 04 | M/brown_rice_long_grain_raw/X | U/-/X | A |
| 05 | G/-/E | U/-/E | C |
| 06 | G/-/E | U/-/E | C |
| 07 | C/-/X | U/-/Q | B, D |
| 08 | M/oats_unfortified_dry/E | U/-/E | A |
| 09 | M/plain_oats_water_cooked_unsalted/X | U/-/Q | A, D |
| 10 | G/-/X | U/-/Q | C, D |
| 11 | M/chicken_breast_skinless_boneless_raw/E | U/-/E | A |
| 12 | M/chicken_breast_meat_roasted/E | U/-/E | A |
| 13 | M/chicken_breast_meat_stewed/X | U/-/Q | A, D |
| 14 | G/-/R | U/-/E | C, F, E, unsafe portion evidence |
| 15 | C/chicken_breast_skinless_boneless_raw,chicken_breast_meat_roasted,chicken_breast_meat_stewed/X | U/-/X | B |
| 16 | G/-/R | U/-/E | C, F, E, unsafe portion evidence |
| 17 | M/whole_egg_raw/E | U/-/E | A |
| 18 | M/whole_egg_hard_boiled/X | U/-/Q | A, D |
| 19 | G/-/X | U/-/Q | C, D |
| 20 | G/-/E | U/-/E | C |
| 21 | M/rice_noodles_dry/E | U/-/E | A |
| 22 | M/rice_noodles_cooked/E | U/-/E | A |
| 23 | M/soba_cooked/X | U/-/Q | A, D |
| 24 | M/soba_dry/E | U/-/E | A |
| 25 | C/-/R | U/-/E | B, F, E, unsafe portion evidence |
| 26 | G/-/X | U/-/Q | C, D |
| 27 | G/-/X | U/-/Q | C, D |
| 28 | G/-/E | U/-/E | C |
| 29 | M/soba_dry/R | U/-/R | A |
| 31 | M/bok_choy_raw/Q | U/-/Q | A |
| 32 | M/bok_choy_boiled_unsalted/E | U/-/E | A |
| 33 | M/broccoli_raw/X | U/-/Q | A, D |
| 34 | G/-/E | U/-/E | C |
| 35 | M/carrot_raw/E | U/-/E | A, E |
| 36 | M/carrot_boiled_unsalted/E | U/-/E | A |
| 37 | C/green_soybeans_boiled_unsalted/X | U/-/Q | B, D |
| 38 | M/green_soybeans_boiled_unsalted/E | U/-/E | A |
| 39 | G/-/X | U/-/Q | C, D |
| 40 | C/firm_tofu_calcium_sulfate_raw/X | U/-/X | B |
| 41 | M/potato_flesh_and_skin_raw/E | U/-/E | A |
| 42 | M/potato_peeled_boiled_unsalted/E | U/-/E | A |
| 43 | G/-/X | U/-/Q | C, D |
| 44 | G/-/E | U/-/E | C |
| 45 | M/sweet_potato_raw/E | U/-/E | A |
| 46 | M/sweet_potato_flesh_baked_unsalted/E | U/-/E | A |
| 47 | M/banana_raw/X | U/-/X | A |
| 48 | G/-/X | U/-/X | C |
| 49 | M/canola_oil_as_sold/E | U/-/E | A |
| 50 | M/canola_oil_as_sold/Q | U/-/E | A, F, unsafe portion evidence |
| 51 | G/-/X | U/-/X | C |
| 52 | G/-/X | U/-/Q | C, D |
| 53 | G/-/E | U/-/E | C |
| 54 | G/-/E | U/-/E | C |
| 55 | G/-/X | U/-/X | C |
| 56 | G/-/X | U/-/Q | C, D |
| 57 | G/-/X | U/-/X | C |
| 58 | G/-/E | U/-/E | C |
| 59 | G/-/X | U/-/Q | C, D |
| 60 | G/-/X | U/-/X | C |
| 61 | G/-/X | U/-/Q | C, D |
| 62 | G/-/X | U/-/X | C |
| 63 | G/-/X | U/-/Q | C, D |
| 64 | G/-/X | U/-/Q | C, D |
| 65 | G/-/X | U/-/X | C |
| 66 | C/-/X | U/-/Q | B, D |
| 67 | G/-/X | U/-/X | C |
| 68 | G/-/X | U/-/X | C |
| 69 | G/-/E | U/-/E | C |
| 70 | G/-/X | U/-/X | C |
| 71 | M/whole_egg_raw/R | U/-/R | A |
| 72 | M/bok_choy_raw/R | U/-/Q | A, F |
| 73 | M/potato_peeled_boiled_unsalted/E | U/-/E | A, E |
| 74 | M/whole_egg_hard_boiled/R | U/-/R | A |
| 75 | M/whole_egg_raw/V | U/-/Q | A, D |
| 76 | M/banana_raw/V | U/-/Q | A, D |
| 77 | C/-/R | U/-/E | B, F, E, unsafe portion evidence |
| 80 | U/-/X | U/-/Q | D |

## Gemini recommendation

**Prioritize deterministic evidence rules and verified catalog coverage.** With the current matcher as the only shortlist provider, a candidate-only Gemini fallback has no direct opportunity to recover any of the 35 missed gold M cases. The one existing shortlist is case 30, where asking the user is already supported. If a separate conservative retriever can produce verified, compatible shortlists, up to 33 of the 35 M misses could be investigated as semantic retrieval opportunities after setting aside the two disputable identity labels (35 and 73). This is a screening ceiling, not an estimate of model accuracy or the cases a model should auto-bind. Zero of the 34 missing references can be supplied by an LLM under this contract, and neither weight evidence nor confirmation can be supplied by model confidence.

First prevent assigning pan or incompatible measurement weight to eaten food. Then improve clause-level aliases, explicit state and basis extraction, and catalog-gap messaging. Add exact, licensed references where coverage matters most and keep unknown household conversions explicit. A later opt-in experiment could compare deterministic-only with deterministic retrieval plus a single semantic suggestion call. Use a fresh, independently reviewed sample split across eligible semantic cases and state, portion and catalog-gap controls. Send only the item and locally verified candidate tokens. Revalidate membership and conflicting evidence server-side and require confirmation. Compare top candidate correctness, correct abstention, calls per entry, confirmation burden, unsafe suggestions, p50/p95 latency and cost per usable suggestion. There is no measured model accuracy, latency or cost here. A model round trip adds latency, potential API charges and review work, with no current evidence that it offsets those costs.
