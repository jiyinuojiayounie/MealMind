# P0.3B-2 food recognition workflow fit

## Current application flow

The application feature is local-development and loopback only. The Log page has three entry paths.

1. **Manual.** Users enter or edit a description and structured food fields. The page sends no recognition request automatically. Quantity and unit are editable inputs. They contain no separate evidence metadata.
2. **Text.** An explicit click sends the description to `POST /api/v1/food-logs/recognize-text`. The Gemini prompt requests a contiguous quote for each consumed item, verbatim name, optional preparation, and optional verbatim portion phrase. It asks for abstention on negation, intention or unsupported inference. The response is validated as `QuotedFoods`. The service checks that the evidence is in the original and that the other fields occur inside the quote, rejects duplicate evidence/name pairs, parses quantities locally, and checks adjacent numeric and sentence context. The endpoint returns the original description, draft-shaped rows, and short notes. Provider failures, timeouts and unavailable service return generic 502, 504 and 503 errors. Quote membership verifies literal grounding. It does not prove that this food, preparation and quantity describe the same consumption event.
3. **Photo.** An explicit click uploads one bounded image. The server validates and normalizes it, then obtains a typed `VisibleFoods` proposal. Gemini can propose a visible label, uncertainty and the count of clearly distinguishable pieces with a bounded unit. It cannot return grams or nutrient values through this schema. The photo cannot establish ingestion. The service suppresses counts for uncertain identity and returns editable fields and uncertainty. The browser handles preview image lifetime. The image is outside the saved log.

The editor preserves the description and replaces existing rows only through its proposal acceptance flow. It carries name, preparation, quantity/unit, a short portion note and possible image identity uncertainty. The typed provider text quote, verbatim portion phrase, the reason a number was withheld, weighing state and context are outside the draft row. The photo count also loses its separate per-item provenance when saving. When saving, the editor submits ordinary food fields and an optional reference binding. UI-only review notes do not persist.

**Identity verification.** The existing structured preview invokes `match_item` on the edited food fields; it accepts an explicit photo uncertainty flag. It suggests compatible USDA records and separately reports portion limitations. Reference confirmation and edible-weight confirmation use explicit user actions. On draft save the server checks the selected ID, reference version, eligibility and item snapshot. Confirmation checks the draft revision and binding before promoting the log. The confirmation itself does not change the saved item fields.

**Nutrition.** Daily analysis reads only confirmed records. A bound item uses the verified reference plus independently valid weight evidence. For mass units the binding path requires the explicit edible-weight flag. There is also a legacy unbound path. It can compute from an exact food record and a recorded positive mass without the separate flag. A saved quantity can therefore reach that legacy path today. In the mock comparison, three rows fit that path without a binding. This is an in-memory calculation demonstration and did not create confirmed logs. Future recognized weight safety must explicitly account for the legacy path.

**New deterministic preview.** The separate `POST /api/v1/food-normalization/interpret` does not run in that workflow. It adds typed source ranges, amount observations, preparation evidence, weighing basis and context such as cooked, purchased, discarded or consumed, along with review codes. It also tries to extract names and simple lists, overlapping with Gemini text extraction. It keeps all observed masses outside its editable proposal, including clear statements of consumption. It does not process photos.

## Proposed evidence-preserving draft contract

Use a transient, optional evidence envelope next to each recognized draft item. Continue accepting existing manual entries and keep storage changes out of the first adapter.

| Concept | Proposed owner and semantics |
|---|---|
| Original expression | Keep the user's unmodified description. Reference a span with source kind and UTF-8 text represented by zero-based Python character bounds with exclusive end, as in the interpretation contract. Use no text span for photos. |
| Extracted identity and preparation | Model-proposed label and verbatim preparation, with separate source spans where grounded. Keep photo identity and count uncertainty explicit. An edited label becomes user-entered and invalidates dependent reference confirmation. |
| Stated amount | Original quantity phrase and unit with parsed observation, which may include multiple values or a range. Preserve contextual 8 g even when the usable amount is unknown. |
| Quantity context and basis | Server-verified origin such as cooking input, purchased, leftover, explicitly consumed, or unknown. Carry raw/dry/cooked weighing state and edible-basis evidence independently. Unresolvable or repeated quotes need review. |
| Editable proposed amount | Prefill 150 g when a statement clearly attributes it to the consumed food, as in `我吃了150g糙米饭`. Use blank for the consumed quantity when `炒菜用了8g油，但锅里还剩一些`. Retain the 8 g in the envelope. Keep household units as stated. |
| Confirmed USDA reference | Existing versioned reference binding, explicit user action, server validation and evidence snapshot. No model-produced reference IDs or conversions. |
| Confirmed edible weight and calculability | Keep explicit attestation scoped to the selected food and weighing state. The number in the proposal never sets the attestation. The deterministic engine alone determines coverage, with traceable food-specific conversions where verified. Protect newly recognized origin from falling through to legacy implicit edible-gram calculation until acknowledged. Unknown remains unknown. |

Use the P0.3B-1 observation/context models and quote position spans as building blocks; avoid invoking its entire food segmentation and label extraction on every recognized item. Return an optional response field that existing clients can ignore. Show one short contextual evidence line in a later UI. A substantial change to the name, portion or preparation should invalidate the dependent confirmation. Keep full photo data out of this contract. Persistence of evidence and a backward-compatible marker for newly recognized unreviewed mass need a separate implementation decision. In particular, the first step must not disable existing manual or historical records by changing the legacy calculator globally.

## Offline comparison

Run from `backend/` with `.venv/bin/python -m scripts.evaluate_food_workflow_fit`. The [diagnostic inputs](food-workflow-diagnostic-v1.json) include four expressions copied from existing automated recognition cases and eight new synthetic text expressions, with 14 expected items. A uses the real backend recognition service while replacing the provider with validated mock outputs. Both A and B invoke the existing matcher. B calls the local interpretation endpoint and parses its response. C is a runner-only combination: replay A's grounded quotes and use one quote-anchored validator rule for an explicit Chinese cooking-use verb. It retains the observation in diagnostics while clearing the editable amount; it is not installed into production. Photo A uses three injected visible-food responses and a synthetic image stub through real preprocessing. There is no B/C image mode. No Gemini response was recorded or measured.

| Result | A text with mocked recognition | B deterministic text | C text with offline validator | A mocked photo |
|---|---:|---:|---:|---:|
| Exact food label | 14/14 | 5/14 | 14/14 | 3/3 |
| Preparation field | 14/14 | 9/14 | 14/14 | 3/3 |
| Exact proposed amount and unit | 13/14 | 4/14 | 14/14 | 3/3 |
| Correctly blank when consumed amount unknown | 4/5 | 2/5 | 5/5 | 2/2 |
| Correct identity outcome and ID | 12/14 | 5/14 | 12/14 | 3/3 |
| Correct exact reference among eligible | 4/4 | 2/4 | 4/4 | 1/1 |
| Required review preserved | 14/14 | 9/14 | 14/14 | 3/3 |
| Unsafe proposed amount | 1/14 | 0/14 | 0/14 | 0/3 |
| Unsafe verified reference | 0/14 | 0/14 | 0/14 | 0/3 |

Items are compared in fixture order. A missing row does not count as correct blank weight. Review is a derived flag for missing edible basis, identity uncertainty, or unavailable reference/portion. All fixture items require some review, so this slice cannot estimate unnecessary clarification. The skipped meal was empty in all text modes. B returned the wrong number of rows in 4/12 text cases. Two fixture rows initially labeled generic rice as unidentified were returned as clarification by the matcher. Clarification is a defensible alternate outcome and the recorded score retains the diagnostic expectation. No frozen evaluation was changed or used to tune this comparison.

The key contrasts are T01 and T02. A/C preserve the explicit 150 g proposal on T01 while generic brown rice still needs a variety check. B preserves it only as an observation. On T02, mock A returns an unsupported 8 g prefill with its generic oil label still unresolved. No incorrect nutrient calculation was measured from T02. B withholds the mass but omits the usable label. C keeps the row, withholds the proposed mass and retains the source observation. This is a one-case demonstration of a validator rule's value. A future evaluation needs independently reviewed cooking, bought/prepared, leftover, mixed-dish and explicit-consumption controls before measuring generalization.

## Recommendation and acceptance criteria

Keep Gemini as the existing extraction path and add narrow deterministic evidence validation. Retain the full interpretation endpoint as a development diagnostic. Do not make it a first-pass router, global preprocessor or automatic fallback now. Whole-sentence replacement costs information and leads to missing lines on this diagnostic. Photo still needs a visual recognition path. Reuse the shared observation model, span checks and portion-context functions. Let the existing structured matcher remain the only reference authority.

1. Add an optional text-recognition evidence envelope, fed by verified provider quotes and sentence context. Start with the tested cooking-use family and at least one independent bilingual control for each context. Detect quote duplicates and conflicts, preserving the raw observation even when editable quantity is blank. No additional model call.
2. In that same implementation phase, define and test the review boundary for recognized weights entering the legacy unbound calculation route. Require explicit acknowledgement in a supported proof path or abstain from calculation for that new unreviewed mass. Preserve already confirmed records and manual compatibility. Keep the proposal/identity/weight actions separate.
3. Before activation, require the clear stated 150 g example to prefill, the cooking/leftover 8 g example to remain blank with evidence, and raw/cooked mismatches and unsupported household conversions to remain uncalculable. Verify unknown photo weights, no automatic binding or meal confirmation, no extra provider calls, and unchanged manual behavior. Test later from recognized proposal through save, explicit confirmation and Today with isolated storage.
