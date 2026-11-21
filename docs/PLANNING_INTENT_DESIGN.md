# Planning intent and Gemini integration

The Day 4 bridge is offline. `PlanningIntent` retains original text, supported structured fields, an explicit-field set, and unresolved issues. `plan_from_intent` maps validated constraints into the deterministic engine and returns a plan, a structured no-feasible result, a clarification requirement, or an unsupported-constraint result. Review eligibility stays inside the backend. [Offline evaluation](../evaluation/PLANNING_INTENT_V1.md)

## Future provider options

| Approach | Latency and cost | Accuracy and safety trade-offs |
| --- | --- | --- |
| Zero calls for recognized requests | Local extraction and composition only. | Small, inspectable vocabulary. Unknown clauses and safety-related statements require clarification rather than guesswork. |
| One model call for intent extraction, then deterministic planning | One model round trip for unresolved general language. Token use can stay low with a narrow typed output. | May improve open-ended recall. Extraction can still omit, misread, or downgrade a constraint. Offer a structured confirmation or correction step. The model supplies candidates, while the backend resolves canonical identifiers and determines eligibility. |
| One model call for personalization over eligible choices | One model round trip after confirmed intent and deterministic filtering. The request includes a bounded shortlist. | Preserves more room for tone and preference personalization. Quality depends on reliable structured intent before the call. The model selects allowed IDs and can explain the result. Reject invalid IDs and recompute constraints server-side. |
| Two stages for extraction and personalization | Up to two sequential calls and two failure points. Stage two can be skipped following clarification, infeasibility, or an adequate deterministic result. | Separates extraction from selection so validation and user confirmation can occur before personalization. Better separation does not guarantee accuracy. Each stage needs an evaluation set, strict schemas, and measured cost and latency. |

Start with zero calls for recognized requests. If a subsequent evaluation supports adding Gemini, use a single targeted call per flow. For unresolved general language, use it for extraction, then compose deterministically after any needed confirmation. For a request already confirmed in structured form, use it for personalization from a validated shortlist if that adds value. Revisit two stages only when a measured quality gain justifies the added latency and cost.

## Validation before live use

- Treat provider output as a proposal. Preserve the original text for the current interaction and attach evidence spans for extracted claims in a future provider schema. Resolve aliases and conflicts independently. Retain unresolved constraints and give the user a way to confirm or correct.
- Require a trusted confirmation step to map each allergy or safety-sensitive statement before planning. A model's confidence or a keyword match cannot authorize that transition. Continue to require reliable recipe and ingredient evidence and assess product labels and cross-contact limitations separately.
- Keep exact inventory restrictions, elapsed-time limits, and dietary exclusions ahead of cuisine, flavor, and diversity. Reject unknown recipe IDs, process-water conflicts, unmet prerequisites, and invalid combinations. Allow optional preferences to go unapplied only when surfaced to the caller.
- Evaluate bilingual extraction, distinct full days, malformed output, contradictory input, unrecognized exclusions, and attempts to override constraints. Measure missed hard constraints per annotated request and inspect failures before any production use. Review draft recipes and publish reviewed evidence before considering live integration.
