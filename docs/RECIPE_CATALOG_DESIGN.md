# Chinese recipe catalog design

Proposed for Day 4 review. Begin with curated data and deterministic planning in the existing FastAPI modular monolith. Gemini personalizes a plan using approved candidates. [Meal planning quality rules](MEAL_PLANNING_QUALITY.md)

## Architecture options

| Option | Fit | Main trade-off |
| --- | --- | --- |
| A. Prompt-only generation | Retain as an evaluation baseline. The current implementation is quick to change and handles free-form requests. | There is limited control over provenance, ingredient mappings, serving conversions, and variety. Output filters can reject problems but cannot supply a trusted alternative. |
| B. Structured recipe catalog, deterministic rules, and Gemini personalization | Recommended. Search a small reviewed catalog by exact IDs, bilingual aliases, roles, and tags. Apply hard filters, combine dishes, then use Gemini for bounded selection and explanation. | Catalog curation and coverage take work. Restricted inventory and sparse categories can produce empty candidate pools. |
| C. Full RAG with vector retrieval | Revisit if real queries frequently miss good matches after alias and tag improvements, or if corpus size and retrieval evaluation justify it. | Adds indexing, embedding and evaluation work. Semantic similarity cannot enforce allergies, inventory, timing or provenance. |

Use versioned structured files in `data/` loaded and validated by the backend. Start with in-memory maps and ordinary filtering and ranking. Keep the catalog repository interface simple enough to change storage later. A database, vector index, paid infrastructure, separate ranking service, or additional agent is unnecessary for the initial corpus.

## Data model

| Record | Proposed fields and rules |
| --- | --- |
| Recipe identity | Immutable opaque `recipe_id` such as `recipe_000042`, `recipe_revision`, and `dish_family_id`. Preserve IDs across translation and ordinary edits. Assign separate IDs for materially different reviewed variants and group related variants into one family. Keep retired IDs resolvable for historical references. |
| Localized recipe | `names.zh-CN`, `names.en-US`, reviewed bilingual steps and optional aliases for search, versioned with the recipe. Keep locale strings out of ranking rules. |
| Categories and roles | Allowed `meal_slots` from breakfast, lunch, dinner, snack. Assign `dish_roles` such as staple, protein component, vegetable component, and accompaniment. Review role coverage for multi-component dishes and tag whether a recipe can stand alone under a given meal template. |
| Cuisine and method | Controlled cuisine and method tags, such as Cantonese-style, steaming, simmering, and stir-frying, plus required equipment and preparation conditions. |
| Canonical ingredient | Stable `ingredient_id`, bilingual display names and reviewed aliases, relevant form or state, and verified allergen relationships where available. Distinguish variants when substitutions, preparation, or safety differ. Ambiguous aliases resolve to unknown until clarified. |
| Recipe ingredient | `ingredient_id`, amount or range, canonical unit, food state, optionality, and `primary` or supporting role. Include water and seasonings. Removing an optional ingredient or substituting an alternative must preserve safety and the recipe's reviewed meal-role coverage. |
| Household measure | Localized label, numeric measure or range, reference amount and unit, ingredient state and size basis, source reference, and confidence such as verified, approximate, or unavailable. Render verified or reviewed approximations only. Keep scale-sensitive pinch or package instructions within their reviewed scope. Never globally equate gram weights to counts or cups. |
| Yield and time | `servings`, reviewed scaling notes, `active_prep_minutes`, `cook_minutes`, `passive_wait_minutes`, `estimated_total_minutes`, and declared starting assumptions. Use a range when variations matter. Explicitly record justified overlap. |
| Dietary and allergen metadata | Verified dietary tags, allergen status per applicable allergen (`contains`, `no_known_source_in_reviewed_recipe`, `unknown`), evidence or reason, and review date. Derive from reviewed ingredients and compound product assumptions where possible. Ingredient or source changes invalidate affected claims pending re-review. |
| Provenance and review | Source kind, author or organization, source URL or internal reference, attribution text, license identifier or permission record, and modification notes. Track `draft`, `reviewed`, or `retired`, reviewer/date, and review scope. Publish only reviewed records with documented reuse rights. Unknown license or limited safety evidence keeps affected content or claims out of recommendations. |

Plan for **80–120 reviewed recipes**, with a working target of 100. A proposed primary classification is 20 breakfast or snack recipes, 25 protein-centered recipes, 20 vegetables, 15 staples, and 20 mixed or one-pot dishes. Secondary tags can overlap. Curate for low-effort single servings, different equipment and methods, commonly available ingredients, vegetarian options, and distinct dish families. Measure whether fixture requests have at least two feasible options before expanding breadth. Begin with a small review batch to validate vocabulary, roles and licensing. No recipe collection or generation is part of this proposal.

## Retrieval and planning flow

1. **Normalize constraints.** Use the existing structured controls and confirmed context first for hard filters. Resolve explicit ingredient IDs through the bilingual alias table. Allow direct lexical matches for simple preferences. Treat unresolved natural-language constraints as unknown. A request for strict exclusions with unresolved mappings requires clarification or a conservative fallback. The single generation may interpret free text over the approved candidates, with no second call for parsing.
2. **Filter and retrieve.** Apply mandatory exclusions, allergen evidence, ingredients by mode, verified time and equipment limits, and requested anchor dishes. Match named dishes by alias and rank the remaining candidates by slot fit, ingredient availability, culinary preference and effort. Candidates with irrelevant unknown metadata may remain eligible when it does not affect a requested constraint.
3. **Combine dishes.** Build a few deterministic feasible combinations per meal, with complete-meal role coverage unless intent calls for an exception. Compare total elapsed time with the user's limit. For full days, rank across slots to discourage repetition. Use bounded search over shortlisted options rather than enumerating the whole catalog across every slot.
4. **Personalize with one bounded Gemini call.** Provide shortlists or complete eligible combinations with IDs, relevant verified facts, and the user's request. Gemini selects from those IDs and localizes the explanation. Return recipe steps, quantities, attributes and time from validated catalog records. Apply only deterministic scaling and reviewed substitutions. Treat invented IDs, ingredients, claims, or edits as invalid rather than publishing unverified model output.
5. **Validate and respond.** Resolve IDs, verify selected revisions and roles, recompute availability, additional ingredients, time and diversity, and check constraints against the selected recipe, including any substitutions. When Gemini times out or proposes invalid choices, use the top deterministic combination only when the backend can attest to all relevant constraints. Otherwise surface the limitation or ask for clarification. Never relax safety constraints or retry generation automatically.

This design favors auditable meal selection. Flexible mode can add ingredients identified in the reviewed recipes. A specific dish outside the catalog may have no supported match. Keep that case visible as an evaluation outcome. A labeled prompt-only fallback would need separate product approval and equivalent validation before release.

## Diversity and future history

- Use stable scoring for a given request and catalog revision. Apply a strong penalty for repeated primary ingredients and methods after excluding unjustified repeated families. Prefer alternates with comparable constraint fit. Keep a low-effort default and respect explicit leftovers or limited-pantry requests.
- For a future approved history feature, store the minimum needed: owner or guest-local scope, recommendation event ID, date and meal slot, recipe revision IDs, derived family IDs and whether a suggestion was explicitly accepted, dismissed, or replaced. Track recommendations and confirmations as different events. Avoid storing raw prompts in history. Use explicit confirmation for AI-proposed persistence, isolate user records, and allow deletion. Guest history can remain local, with confirmed migration if implemented.
- As a starting hypothesis, downrank families offered in the last seven days, with greater weight for recent accepted meals. Time window, storage and feedback policy require review. Keep diversity checks within the current day when there is no history. Do not create a history store in this step.

## API and schema impact

Keep `POST /api/v1/meal-plans/generate` and its current Pydantic request and success payload for the first implementation slice. Retain `single_meal`, `full_day`, the optional meal type and cooking limit, supported language values, and the current `infer_scope` behavior. Resolve catalog IDs inside the backend. Preserve `title`, `meals`, `dishes`, `ingredients`, `instructions`, `explanation` and `additional_ingredients`. The current `estimated_preparation_minutes` field is effectively total estimated time. Retain that meaning for compatibility. Use elapsed time for the existing limit. An explicit cooking-only request can be represented in internal intent and shown separately in a later payload.

Internal models would add validated recipe and ingredient records, meal intent, candidate combinations, and a provider schema for selecting candidate IDs. Return the current numeric quantity and unit until a reviewed display field is exposed. Preserve the current existing/flexible request modes. The PRD's update mode remains a future confirmed pantry workflow.

Potential additive fields include recipe ID and revision, ingredient ID and portion label, per-meal prep/cook/total times, and source metadata. Before exposing these fields, check strict downstream consumers because the current Pydantic response forbids extras. Typed partial or clarification outcomes also need API and UI review. A compatible first slice can keep the existing generic error path for infeasible plans. Review a versioned or opt-in extension before shipping richer outcomes.

## Product-owner review

Approve the catalog-first default and policy for catalog misses, first curation categories and source eligibility, and the initial quality gates. Confirm whether to expose portion labels and time breakdowns in the first API extension. Decide whether and when owner-scoped history and richer clarification responses are in scope. Record approved decisions in the decision log before changing the PRD or implementation.
