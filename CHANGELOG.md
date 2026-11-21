# Changelog

## Unreleased

### Added

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
