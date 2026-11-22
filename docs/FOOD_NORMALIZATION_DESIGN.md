# P0.1 Food normalization and reference matching

Design proposal for review. Intake remains based on confirmed logs under FR05, FR07 and D020. [PRD](PRD.md) · [Decision record](DECISIONS.md)

## Current boundary

Text recognition extracts food and explicit portion phrases from evidence in the user's original words. Image recognition proposes visible food, uncertainty and occasional piece counts. Both return editable proposals, and neither establishes an edible gram weight or writes a confirmed log. Manual and AI-assisted entries share the same item editor and confirmed log schema. The current item stores a name, optional quantity/unit and optional preparation method. It has no canonical reference, independently confirmed portion provenance, or explicit raw/cooked field. The log's optional original description stays separate.

The current nutrition engine matches reviewed names and aliases, a small set of preparation-qualified combinations, and verified portion references. The v1 dataset has 30 USDA food-state records and three narrowly defined portion records. Daily analysis reads confirmed records, shows nutrient-specific coverage, and performs no model calls. A successful food match and a calculable quantity are independent.

## Recommended flow

1. Build one backend matching service receiving a structured item from manual entry, text recognition or image recognition. Retain the original label and log description. Form editing and analysis can call the same deterministic resolver. In analysis, use an existing reviewed binding when one exists, otherwise resolve deterministically from the stored item's evidence. Never mutate confirmed logs. Do not reparse the entire original description to insert foods into confirmed history.
2. Normalize Unicode, whitespace, case, punctuation variants, and reviewed bilingual synonyms. Separately identify food identity, preparation, measurement state, edible basis, and literal quantity/unit evidence. Keep each constraint and its origin. Apply only reviewed implications, for example a phrase for cooked noodles establishes the cooked state. It does not establish rice-versus-wheat identity or portion weight.
3. Retrieve a small set of local reference candidates from a versioned mapping index. Gate on identity, state, preparation and edible basis. Only an unambiguous exact rule with sufficient evidence can automatically bind. Use lexical similarity to offer candidates, not to select one. Never promote fuzzy similarity, model confidence, or the only available row into evidence. Report a known covered family with missing qualifiers separately from a known food without a compatible reference or an unidentified phrase.
4. Add optional Gemini assistance after the deterministic path is evaluated. Call it only on an explicit draft-review action when a bounded candidate shortlist exists and interpreting the phrase might change the outcome. Send the relevant item phrase, its structured qualifiers, and curated candidate labels. Exclude full history, photos, log IDs and free-text portions unrelated to the item. Use one call per review batch, no hidden retries, and the existing server-side provider configuration. Return bounded candidate tokens, source phrase evidence, or abstention. Validate membership, evidence and conflicts server-side. In the first hybrid release, semantic suggestions require user confirmation; only deterministic rules can auto-bind. A spelling mistake with a usable shortlist can be shown locally without a model.
5. Resolve quantity independently. Record explicit units and amounts without changing them, including one piece, half a bowl, or unknown. Use the existing deterministic conversion path only for edible mass and verified food-specific factors whose descriptors match. Do not convert count or volume with model output. Send validated reference binding and portion to the existing nutrient calculator. Keep missing values null and preserve partial totals and provenance.

## Matching rules and UX

| Situation | Outcome |
| --- | --- |
| Explicit, compatible Chinese/English label or alias | Bind automatically with provenance. Show the matched option in the item editor, with a way to correct it before confirmation. |
| “150g鸡胸肉” | Preserve 150 g. Ask which preparation and whether the amount applies to the reference's skinless meat when that is unclear. Never swap raw and cooked reference rows. |
| “半碗糙米饭” | Preserve 0.5 bowl and recognize cooked brown rice. Ask about grain type only if it affects reference selection. Even if a long-grain row is selected, show that the bowl weight is unavailable. |
| “一个水煮蛋” | Recognize a boiled egg and the count. Check that the hard-boiled reference fits if doneness is unknown. Generic pieces have no default weight. Ask whether it matches the verified size only if useful, or let the user continue with unknown weight. |
| “一盘青菜” | Keep the dish and unit. Ask which vegetable if the user knows; there's no plate-to-gram default. |
| “炒鸡蛋”, “拿铁咖啡”, “海南鸡饭” | Mark catalog gaps for the current snapshot. Do not replace with raw egg, plain milk or separately assumed rice and chicken. Mixed dishes may use an exact reviewed dish reference in a later release. |
| Conflicting evidence or unclear photo identity | Ask a focused question or show at most a few verified candidates. If no safe choice is possible, leave unresolved. A confirmed meal establishes what the user recorded, not the precision of photo estimates. |

Keep the item editor compact. Show one short line below a row when attention is needed. Offer the most consequential clarification first, group remaining issues inside the item, and allow saving or confirming as eaten without completing nutrition fields. Use plain-language prompts such as “Was the 150 g weighed raw or cooked?” or “No verified weight for this bowl; leave it as half a bowl.” Do not direct users to edit confirmed records in the existing draft editor. In Today, show why a confirmed item is missing an estimate without changing it.

## Proposed contracts and storage

- Add a local-development, no-store `POST /api/v1/food-normalization/preview` with bounded items and explicit deterministic or assisted mode. Each item carries its index, label, preparation, quantity and unit, plus optional user-confirmed state/edible basis. The preview writes nothing and returns separate `identity_status` (`matched`, `needs_clarification`, `unidentified`, `unsupported_reference`) and `portion_status` (`edible_mass`, `verified_conversion`, `quantity_unknown`, `conversion_unavailable`, `needs_review`). Include stable reason codes, reviewed candidate IDs and labels, reference/index versions, derivation method, and matching evidence. Provider timeout or invalid output leaves deterministic results available. Never log private item text.
- In a later integration, expose optional matching proposals on recognition results or invoke the same service against edited draft rows. Persist only an optional user-accepted binding with internal food-state ID, reference and mapping versions, state/preparation, and portion provenance if applicable. Keep original name, description, quantity and unit. Validate an accepted binding against the active dataset and current item evidence at draft save/confirmation; any name, state or portion edit invalidates the affected binding. For legacy rows, optional fields are absent. Confirmed rows and their revisions stay untouched. Define how older bindings resolve against versioned snapshots; if unavailable or incompatible, report unresolved rather than substitute.
- Keep the nutrient snapshot unchanged. Add reviewed aliases, state evidence and mapping metadata in a separate versioned index linked to stable reference food IDs. Validate cross-references and collisions during load, and retain explicit catalog gaps where known. Later partitions can add regional foods and licensed sources without conflating raw/cooked or changing the arithmetic. Start with exact indexes and bounded lexical shortlist retrieval; avoid vector infrastructure until evaluation demonstrates a need.

## Evaluation and stages

Use the [50-case fixture design](../evaluation/FOOD_NORMALIZATION_V1.md), report modes and languages separately, and keep audited correctness separate from reference coverage. Mock model outputs before enabling assistance. Re-run the v1 nutrition and log regressions, including stale draft proposals, unchanged confirmed history, stable reference/portion validation, mixed-dish abstention, and genuine zero versus unknown.

1. Review gold cases and alias policy, then build the deterministic resolver and offline evaluation. Keep the original nutrient snapshot and calculation arithmetic.
2. Add preview contracts and a bilingual draft-review UI. Test state clarification, manual/AI consistency, no writes from preview, and snapshot mismatch. Only then allow optional reviewed bindings on new or edited drafts.
3. Measure deterministic recall and unnecessary questions. If useful, test one bounded Gemini call against an offline mock and, after approval, a separate controlled evaluation. Retain it only if it improves suggestions without reducing safety or exceeding the call/latency budget.
4. Expand verified references based on catalog-gap counts. Defer free-form mixed-dish decomposition, automatic gram estimation, changes to confirmed records, and vector retrieval.

The central tradeoff is fewer missed matches versus false equivalence. A narrow reviewed alias rule should remove avoidable questions, while uncertain food state and truly absent reference rows require different user messages. A coverage gap is a dataset issue; another model call cannot supply missing evidence.

## P0.2A offline implementation

`FoodNormalizer.match_text` accepts a single standalone food expression. `match_item` accepts the shared food-log item and can abstain on an explicitly uncertain recognition. The returned identity outcomes are `matched`, `ambiguous_identity`, `food_state_unknown`, `unsupported_food`, and `insufficient_information`. A verified portion outcome identifies the existing USDA serving row. It supplies no gram estimate. An explicit mass is separately recorded and does not authorize calculation when identity is unresolved.

Run the held-out cases from `backend/` with `.venv/bin/python -m scripts.evaluate_food_normalization`. The evaluator reads the original Markdown labels and reports identity and portion separately. Unknown expressions and enumerated catalog gaps have distinct outcomes. The alias layer and runner are offline. The nutrition calculator, HTTP endpoints and confirmed log history continue to use their existing behavior.

## P0.2B local preview

`POST /api/v1/food-normalization/preview` takes an object with 1–50 `items`. Each entry contains an existing structured `item` and an optional boolean `identity_uncertain` for recognition proposals. It returns an ordered list of normalization results, including the original item name, supplied quantity (decimal string or null), identity and portion statuses, clarification code, matching rule, verified candidates and reference provenance. An ambiguous item has no bound reference. A serving specification identifies a verified source row without returning an estimated weight.

The route uses the Food Logging development and loopback checks and returns `Cache-Control: no-store` on success. The request sends current item fields and uncertainty only. The description, log IDs, photos and full history stay outside the request. Log requests a preview only on a button click. Users may choose a candidate for review without changing the draft fields. Choices are temporary and reset whenever food items change or the editor closes.

A later integration needs versioned, user-confirmed reference bindings on draft items. The backend should validate the selected reference and portion evidence and invalidate or revalidate the binding on changes to identity, preparation or quantity. The calculation path can then read compatible bindings from confirmed records while preserving legacy behavior for records without a binding. Preview choices are currently excluded from storage and Today analysis.

## P0.2C-1 persisted reference bindings

Food-log draft create and update accept an optional item-level `reference_binding`. Send only the selection fields below, with the original item unchanged. The nested `item` is the snapshot from the preview and confirmation step. It uses the same four food-item fields. A draft edit with no selection for an item clears that item's binding. Send the normal `expected_revision` with updates.

```json
{
  "name": "鸡胸肉",
  "quantity": 150,
  "unit": "g",
  "preparation_method": null,
  "reference_binding": {
    "food_id": "chicken_breast_skinless_boneless_raw",
    "reference_version": "usda-sr-legacy-v1",
    "confirmed": true,
    "edible_weight_confirmed": true,
    "item": {
      "name": "鸡胸肉",
      "quantity": 150,
      "unit": "g",
      "preparation_method": null
    }
  }
}
```

P0.2C-2 should display the selected catalog name, food state and preparation and ask the user to confirm that these details describe the entry. For mass units, ask separately whether the recorded amount is edible weight in the selected state. Leave `edible_weight_confirmed` false if the user is unsure. A confirmed identity can still be saved without nutrition coverage. A household unit requires an applicable reviewed specification, such as the existing USDA large egg unit. Render the review controls only in local development.

On a draft write the server verifies the catalog version, item snapshot and membership in the current deterministic matches or candidates. The server adds its binding version, FDC ID, state, preparation, source release and confirmation timestamp. Those output fields must be stripped when resubmitting a binding. The food-log confirm operation rechecks the saved binding and the normal record revision before changing the meal status. A rejected binding returns HTTP 422 with `detail.status = food_reference_binding_rejected`, zero-based `item_index`, and a reason such as `item_changed`, `reference_not_applicable`, or `catalog_version_unavailable`. The frontend should request a fresh preview for a changed item, keep each selection attached to its row when reordering, and let the user clear an invalid binding and retry. The draft editor submits only selection fields, retains unchanged selections when reopening a draft and clears an item confirmation when its food fields change.

Only confirmed logs participate in Daily Nutrition. A valid binding resolves identity before weight calculation. Bound mass needs the separate edible-weight confirmation. Verified portions resolve to the existing food-specific source row, using the original nutrient formulas. Invalid, stale or unavailable bindings produce item review codes and no estimate for that item. Entries without a binding still use the previous lookup. Bindings live in the existing SQLite JSON document and require no table migration or rewrite of earlier records.


## P0.2C-2 confirmation in the draft editor

The preview response exposes `requires_edible_weight_confirmation` to identify entered mass independently of food matching. This flag asks for evidence and conveys no estimate. The editor tracks selections per row and retains a saved binding only while the four recorded item fields still agree with the binding snapshot. The draft save and consumption confirmation remain distinct actions. Today localizes the review reasons for unusable bindings on confirmed entries.
