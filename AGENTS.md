# MealMind development instructions

## Product and scope

- Use [the PRD](docs/PRD.md) and [the decision record](docs/DECISIONS.md) to establish product scope. Record approved changes and scope cuts in the decision record. Keep the original Word baseline intact.
- Preserve the Plan → Track → Analyze → Replan loop and independent entry points. Keep profile creation optional, onboarding choices equally prominent, and core flows available to guests.
- Keep changes incremental. Implement and verify one feature or coherent slice before starting the next. Report actual implementation and verification status.
- Keep native apps, formal WeChat mini program release, commerce, precise inventory accounting, social features, subscriptions, complex health reporting, gamification, general-purpose chat, and autonomous background agents outside the MVP.

## Architecture and conventions

- Maintain a GitHub monorepo with a React, TypeScript, Vite, Tailwind CSS, and i18next frontend and a Python/FastAPI modular monolith. Communicate over HTTPS and REST in deployed environments.
- Put UI, interaction state, separate Simplified Chinese and English translation resources, and guest-local persistence in the frontend. Use English for code, identifiers, and technical documentation. Keep localized UI copy out of application logic and use canonical ingredient IDs across locales.
- Put API validation, authorization, shared business rules, deterministic nutrition, and model integration in the backend. The global assistant and feature screens share the same services. Route intents to a bounded set of typed tools.
- Use Supabase PostgreSQL and Supabase Auth for authenticated persistence. Put versioned schema and access-policy changes in `supabase/migrations/`. Keep meal records and pantry snapshots independent and scope authenticated data to its owner.
- Keep data provenance, licenses, and nutrition units with imported reference data. Keep model evaluation fixtures and scoring in `evaluation/`. Use Gemini as the initial model candidate, with the model version subject to evaluation. Target Render for deployment.
- Keep credentials in environment configuration. Only expose intentionally public values to the frontend. Vite-prefixed values are browser-visible. Keep privileged Supabase credentials and model keys server-side.

## Safety and data handling

- Use structured nutrition sources and deterministic Python code. Validate units, raw versus cooked state, edible portions, and plausible quantities. Surface missing data, uncertain portions, and unknown allergens. Treat photo-derived amounts as estimates.
- Validate ownership, inputs, and business rules server-side before persistence. Present AI-proposed database writes, updates, and deletions for explicit user confirmation before execution. Apply the same confirmation boundary to guest-local persistence. Make retried confirmed operations safe against duplicate records.
- Preserve confirmed food logs during replanning. Adjust only unexecuted meals, and treat missing intake records as unknown. Never recommend skipping meals or severe restriction to compensate for earlier intake.
- Minimize personal and health data collection. Avoid exposing sensitive data or secrets in logs, fixtures, and model requests. Keep nutrition guidance informational and out of medical diagnosis or treatment.
- Bound model calls and retries. Report model or tool failures accurately and give users a retry path.

## Verification

- Run relevant tests before moving on. Report any checks that could not run.
- For frontend changes, verify affected flows at mobile widths and in both languages. For backend changes, cover normal behavior, invalid inputs, and authorization where applicable.
- For nutrition changes, use deterministic fixtures for known values, conversions, and missing data. For persistence changes, verify owner isolation, confirmation, duplicate submissions, and migration behavior as applicable.
- For AI changes, use local fixtures or mocked model responses for intent routing, ambiguity, confirmation, refusals, uncertainty, and failure handling. Track model quality separately in `evaluation/`.
