# Product backlog

These improvements follow the first end-to-end MVP core loop (Plan → Log → Analyze → Replan). Review every item before a production-quality release. P0 items are release criteria. P1 items require a documented acceptance or an explicit product-owner decision to defer them further.

| Priority | Deferred issue | Production-quality review |
| --- | --- | --- |
| P0 | Food normalization and reference matching (P0.1) | Review the bilingual, state-aware matching design and 50-case evaluation. Separate food identity, catalog gaps and portion conversion. Preserve original logs and use verified reference candidates only. [Design](FOOD_NORMALIZATION_DESIGN.md) |
| P0 | Complete-meal quality and verified portions | Review complete lunches and dinners for practical protein, staple, and vegetable coverage. Verify edible weights and serving sizes before using portions in nutrition estimates. |
| P0 | Cooking effort and practical one-person templates | Cook through representative single-serving meals and check declared prerequisites, elapsed time, and independently prepared dishes. Revalidate convenience ranking against those estimates. |
| P1 | Breakfast simplicity | Curate and test combined breakfasts and cooked dishes with ready-to-eat accompaniments. Check whether they reduce separate cooking work while covering the intended breakfast roles. |
| P0 | Catalog expansion and recipe verification | Review a diverse set of dishes for ingredients, steps, quantities, roles, times, and provenance. Keep unreviewed recipes out of production retrieval. |
| P1 | Cross-generation dish repetition | Evaluate repeat recipe and family IDs over multiple requests. Define guest and authenticated history scope before storing recommendation history. |
| P1 | Human-friendly ingredient measures | Verify household equivalents by ingredient state and portion size, keeping standard quantities as the reference. |
| P1 | Result UI improvements | Test bilingual mobile readability, ingredient and prerequisite visibility, time estimates, and navigation through structured results. |
| P1 | Compact food-log item editor | Make each item collapsible with a short name and quantity summary. Keep edits and uncertainty warnings visible, preserve keyboard access, and expand invalid rows on submit. |

See the [meal planning quality rules](MEAL_PLANNING_QUALITY.md) and [recipe catalog design](RECIPE_CATALOG_DESIGN.md) for existing detail.
