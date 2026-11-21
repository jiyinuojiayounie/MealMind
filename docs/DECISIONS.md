# MealMind decision record

The Day 1 entries retain the IDs and status from [PRD v1.1](PRD.md). Add dated entries for approved changes, with the rationale and any superseded decision IDs.

| ID | Decision |
| --- | --- |
| D001–D003 | Ship quickly at low cost to validate with real users. Keep architecture proportional to the product and use discovery to establish direction. |
| D004 | Launch the web MVP first. Reuse the backend for a later WeChat mini program, subject to eligibility and review. |
| D005–D007 | Give both onboarding choices equal weight. Support full-day and single-meal planning and keep pantry management independent. |
| D008–D009 | Use low-maintenance ingredient snapshots and let guests try the core flows before registration. |
| D010–D011 | Support existing, update, and flexible ingredient modes and ship Simplified Chinese and English. |
| D012 | Use the confirmed stack in a GitHub monorepo with a separate frontend and modular FastAPI backend. Develop incrementally and target GitHub-driven Render deployment. |
| D013 | Put a global assistant on Today and share controlled intent routing and tools across feature screens. The detailed v1.1 workflow is a proposed baseline. |

## Day 2 foundation

- The current step covers directories and documentation. Runtime scaffolding, dependency setup, migration SQL, and Render configuration are deferred. The PRD roadmap also describes frontend and backend initialization under Day 2.
- Environment variable names in the root template are proposed conventions for future implementation.

The [PRD open questions](PRD.md#open-questions) remain pending.

## Day 4 recipe catalog foundation

The following proposals record the approved product direction and the implementation boundaries for review.

| ID | Proposed decision |
| --- | --- |
| D014 | Default complete lunches and dinners to protein, staple, and vegetable roles, including coverage by a single combination dish. Distinguish complete meals from individual dishes and preserve explicit request intent. Leave calorie restriction out of the default. |
| D015 | Treat allergy exclusions, explicit restrictions, and strict ingredient availability as hard constraints. Missing or unverified allergen evidence is insufficient for exclusion-sensitive retrieval. Conduct further safety validation for allergy-related input, aliases, product labels, and cross-contact before live use. |
| D016 | Prevent repeated dishes within a plan by tracking recipe and family IDs. Retain stable IDs to support future cross-generation deduplication after history scope and consent are approved. |
| D017 | Store standard quantities and preparation states. Show household measures only when supported by reviewed references tied to the specific quantity, unit, and ingredient state. |
| D018 | Use a curated catalog and deterministic filtering and validation, with one Gemini call for personalization over approved candidates. Seed a small development catalog and exclude draft and retired recipes from production retrieval. Defer live endpoint integration. |
