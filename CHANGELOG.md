# Changelog

## November 26, 2026 · Public AI Planning

- Enabled live Gemini Smart Planning on the public portfolio site through a dedicated Render Free API with shared Redis quotas.
- Verified Chinese meal generation, explicit browser-local save, and persistence after refreshing Today. Food logging, nutrition analysis and replanning remain browser-local.


## Unreleased

### Added

- Added local-development meal photo recognition with bounded image uploads, metadata stripping, and editable draft suggestions. Recognition makes no food-log writes.

- Established the Day 2 monorepo directory structure and project documentation.
- Preserved the original Word PRD and added an English Markdown baseline.
- Documented product and architecture decisions, local ignore rules, and placeholder environment configuration.
- Initialized the React and TypeScript frontend with Vite, Tailwind CSS, and React Router.
- Added six screens, four mobile navigation tabs, equal onboarding choices, and the Today assistant preview, shortcuts, and meal overview.
- Added Simplified Chinese and English translations, a persistent language switch, and labeled previews for features awaiting the backend.
- Documented local frontend startup, linting, and build commands.
- Added a modular FastAPI backend with pinned dependencies, environment-based settings, local CORS, OpenAPI docs, and a tested health endpoint.
- Connected the frontend through a typed API client and added a bilingual, development-only API status indicator with retry.
- Documented separate frontend and backend startup commands and local environment overrides.
- Added Gemini-backed meal planning for single meals and full days with structured responses, bilingual output instructions, and server-side ingredient and time checks.
- Added mocked API tests for request validation, missing configuration, provider failures, and invalid model output.

## v0.2.1

- Completed the public browser-local Plan → Log → Analyze → Replan workflow. Manual food logs separate drafts from confirmed consumption, and nutrition reports verified estimates with coverage information.
- Added deterministic local meal replacement from the nine reviewed candidates, with explicit acceptance, meal locks, stale-state checks and plan history.
- Prepared the opt-in Gemini 3.5 Flash-Lite planning service with a successful isolated real-model browser test. Public AI activation remains off.

## v0.2.0-demo.1

- Introduced a static portfolio build with nine selected Blind Box recipes, explicit dietary-restriction handling, and browser-local meal plans.
- Added a single current daily plan view with separate version history and explicit review of the existing and proposed meals before replacement.
- Labeled public planning, nutrition and replanning examples. Kept Gemini, food logs and other private endpoints out of the demo deployment.
- Simplified Smart Planning to one natural-language flow in local development. Planning and Replan expose no recommendation-mode selector. The public demo keeps a labeled sample, and catalog planning remains available for developer testing.
