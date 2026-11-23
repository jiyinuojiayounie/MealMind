# Product backlog

These improvements follow the first end-to-end MVP core loop (Plan → Log → Analyze → Replan). Review every item before a production-quality release. P0 items are release criteria. P1 items require a documented acceptance or an explicit product-owner decision to defer them further.

| Priority | Deferred issue | Production-quality review |
| --- | --- | --- |
| P0 | Protect consumed-weight evidence (P0.2D) | Abstain on pan input and measurement-state or edible-basis conflict. Add regression fixtures before broadening food identity matching. |
| P0 | Improve food normalization beyond exact labels | Parse explicit state and preparation clauses, recognize reviewed bilingual synonyms, and separate known catalog gaps from unresolved identities. Evaluate changes on a new independently reviewed sample. [Holdout results](../evaluation/FOOD_NORMALIZATION_HOLDOUT_V1_REPORT.md) |
| P1 | Expand verified nutrition reference coverage | Prioritize common staples, beverages and nonmatching preparations by usage evidence. Add only traceable compatible references and serving conversions. |
| P1 | Measure optional semantic matching | Defer until deterministic retrieval produces usable verified shortlists and weight safety passes. Use a controlled opt-in comparison with server validation and user confirmation. |
| P0 | Complete-meal quality and verified portions | Review complete lunches and dinners for practical protein, staple, and vegetable coverage. Verify edible weights and serving sizes before using portions in nutrition estimates. |
| P0 | Cooking effort and practical one-person templates | Cook through representative single-serving meals and check declared prerequisites, elapsed time, and independently prepared dishes. Revalidate convenience ranking against those estimates. |
| P1 | Breakfast simplicity | Curate and test combined breakfasts and cooked dishes with ready-to-eat accompaniments. Check whether they reduce separate cooking work while covering the intended breakfast roles. |
| P0 | Catalog expansion and recipe verification | Review a diverse set of dishes for ingredients, steps, quantities, roles, times, and provenance. Keep unreviewed recipes out of production retrieval. |
| P1 | Cross-generation dish repetition | Evaluate repeat recipe and family IDs over multiple requests. Define guest and authenticated history scope before storing recommendation history. |
| P1 | Human-friendly ingredient measures | Verify household equivalents by ingredient state and portion size, keeping standard quantities as the reference. |
| P1 | Result UI improvements | Test bilingual mobile readability, ingredient and prerequisite visibility, time estimates, and navigation through structured results. |
| P1 | Compact food-log item editor | Make each item collapsible with a short name and quantity summary. Keep edits and uncertainty warnings visible, preserve keyboard access, and expand invalid rows on submit. |

See the [meal planning quality rules](MEAL_PLANNING_QUALITY.md) and [recipe catalog design](RECIPE_CATALOG_DESIGN.md) for existing detail.
