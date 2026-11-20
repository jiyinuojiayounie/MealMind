# MealMind product requirements

English Markdown baseline from the [original Word PRD v1.1](MealMind_PRD_v1.1.docx), dated 2026-11-20. The requirements and metrics describe MVP goals.

## Product positioning and objectives

MealMind helps Chinese students abroad, young professionals living alone, and other Chinese-speaking users decide what to eat. The product addresses difficulty combining ingredients, plans that do not suit Chinese eating habits, disrupted schedules, and the effort of food logging and pantry upkeep.

The product combines Chinese-food-first planning, multimodal logging, and adaptive replanning. Users can personalize without creating a body profile, entering ingredients, registering, or logging daily. Release a mobile-first web MVP first. Consider a WeChat mini program later, subject to eligibility and review.

The Day 1 estimate was 7–10 development days for the first public web MVP, with an initial budget target of S$0–20. Actual model and operating costs require verification. Expected project deliverables include a live demo, GitHub repository, English README, PRD, English product case study, AI evaluation report, real user feedback and iteration records when available, a 1–2 minute English demo video, and an English résumé entry. Market assumptions and target metrics remain to be validated.

## Experience

The core loop is **Plan → Track → Analyze → Replan**. Users can begin anywhere. Single-meal planning can use confirmed records for the same day and also works without history.

| Screen | Main interactions |
| --- | --- |
| Welcome | Equally prominent profile creation and direct start choices, language switching, and guest access |
| Today | Brand, date, language switcher, lightweight Assistant input and direct start, cards for planning, logging, pantry, and personal settings, today's plan, and optional nutrition overview |
| Plan | Full-day or single-meal planning, three ingredient modes, natural-language requests, and plan details and revisions |
| Log | Photo or text logging, recognition review, nutrition estimates, and adjustment of remaining meals |
| Pantry | Timestamped ingredient snapshot, additions and removals, and full refresh |
| Profile | Profile, preferences, language, account, and data management |
| Assistant | Intent routing through shared tools, text or structured cards, and confirmation before writes |

Bottom navigation contains Today, Log, Pantry, and Profile. Today is the entry to planning and the Assistant. Account and language settings retain explicit controls. A new user can choose an onboarding path, plan a day or meal, review the plan, confirm an actual meal, and adjust the remainder. A returning user can plan from Today or the Assistant and reuse, refresh, or bypass the snapshot without backfilling missed days.

## Functional requirements

P0 denotes a first-release target. Prioritize the core loop if delivery is constrained and record any scope cuts.

### FR01 Equal onboarding choices (P0)

Offer equal screen area and visual weight to creating a profile for nutrition guidance and starting directly to decide what to eat. Both paths afford the same core capabilities, and users can switch later.

### FR02 Optional profile (P0)

Support editable and deletable preferences, exclusions, allergies, equipment, available time, and nutrition needs. Adults may opt into a reasonable energy-needs reference based on inputs such as age, height, weight, and activity. Casual eating mode hides calorie goals by default. Rapid weight loss is outside scope.

### FR03 Ingredient snapshot (P0)

Store the latest confirmed ingredient list and timestamp, allowing unknown quantities. Accept natural-language entry, additions, removals, and full replacement. Prompt when the snapshot is stale. Keep history backfill optional and avoid inferring or automatically deducting consumption from plans or meals eaten out.

### FR04 Meal planning (P0)

Plan a full day or a meal such as breakfast, lunch, dinner, or a snack. Accept natural-language constraints about preferences, schedule, budget, time, and equipment. Favor Chinese dishes, single servings, and simple preparation.

| Mode | Behavior |
| --- | --- |
| Existing | Show the latest snapshot timestamp, confirm availability, and plan from the list. |
| Update | Accept a short description, refresh the snapshot after confirmation, and use it for planning. |
| Flexible | Allow ingredients beyond the snapshot while preserving it. Users can shop independently. |

Return dishes, ingredient quantities, preparation steps, estimated time and nutrition, and substitutions where needed. Surface conflicts and missing data, and accept natural-language revisions. A basic shopping reference is a P0 candidate. Live pricing and ordering are outside scope.

### FR05 Food logging (P0)

Accept photos and text. Use a multimodal model to identify dishes and estimate portions, then save after user confirmation or correction. Display ranges when oil, hidden ingredients, or weight are uncertain, and flag unknown ingredients. Users can log current meals without backfilling history.

### FR06 Adaptive replanning (P0)

Use today's confirmed meals, current needs, ingredients, and preferences to adjust unexecuted meals and explain the changes. Preserve confirmed records and flag incomplete data. Missing records represent unknown intake. Never recommend skipping meals or excessive restriction to compensate for previous intake.

### FR07 Nutrition engine (P0)

Compute nutrition deterministically in Python using structured data. Normalize units, raw and cooked state, and edible portions. Validate portion sizes, ingredient constraints, allergen risk, and plausibility. Report photo-derived nutrition as an estimate.

### FR08 Guest-first authentication (P0)

Provide core features to guests and store guest profiles, snapshots, and records locally. Explain that clearing browser data can erase them. Support cloud storage, cross-device sync, and explicitly confirmed guest migration after registration. Isolate users' data and support deletion.

### FR09 Simplified Chinese and English (P0)

Switch UI, navigation, forms, prompts, and errors immediately and persist the language preference. Accept mixed-language input and default new generated content to the active language. Use canonical ingredient IDs and bilingual ingredient names. Retain the original language of historical long-form text for the MVP.

### FR10 Global AI Assistant (P0, added in v1.1)

Provide lightweight input and direct start on Today. Route planning, logging, pantry, preferences, nutrition analysis, and replanning through shared business services. Support multi-intent requests, images, and structured action cards. Confirm proposed writes and redirect unrelated requests to meal planning and nutrition. Use fixed tools and controlled workflows. Complex autonomous conversations, automatic background tasks, and general chat are outside the MVP.

## Assistant workflow and safeguards

The global entry handles open-ended requests. Feature screens provide contextual forms and actions. Both use shared state, data, and services through one controlled workflow.

| Tool | Behavior |
| --- | --- |
| `plan_meals` | Generate a meal plan without deducting inventory. |
| `update_pantry` | Preview additions or replacement and save after confirmation. |
| `log_meal` | Propose dishes and portions for confirmation. |
| `analyze_nutrition` | Use confirmed records and identify gaps. |
| `replan_meals` | Adjust remaining meals. For dining out, suggest dishes only. |
| `update_profile` | Preview preference changes and save after confirmation. |

Parse structured intents, arguments, and order. Read authorized context, invoke allowed tools, and use Python for deterministic computation and rule validation. Where a write is needed, get confirmation before persistence. Return structured cards and explanations. For a combined lunch log, pantry update, and dinner request, propose and confirm the log and update before planning from the saved state. Keep unconfirmed information in the current draft only.

The backend verifies identity and authorization. Clarify or flag stale ingredients, unknown allergens, uncertain portions, and missing data. Surface retryable errors when models, networks, or tools fail. Bound calls, retry counts, and costs, and prevent duplicate persistence from repeated submissions. Minimize body data collection and keep nutrition guidance informational. No additional commercial APIs or multi-agent architecture are required.

## Technical architecture

- Use VS Code and Codex with a GitHub monorepo. Build the frontend with React, TypeScript, Vite, Tailwind CSS, and i18next.
- Use a Python/FastAPI modular monolith over HTTPS and REST. Share the backend with a future mini program. Organize business logic around intent routing, planning, logging, replanning, pantry, profile, and nutrition.
- Use Supabase PostgreSQL and Supabase Auth, with local guest storage. Candidate tables include `users`, `user_profiles`, `pantry_items`, `food_nutrition`, `recipes`, `meal_plans`, and `meal_logs`. Keep snapshots and meal history independent, isolate data by user, and finalize the schema during implementation.
- Evaluate Gemini first using multimodal input, a Python SDK, structured output, and tool calls. Select the model version after testing. Keep private API keys in the backend environment.
- Prefer clearly licensed food composition data such as USDA FoodData Central and Chinese recipe sources such as HowToCook or original recipes, subject to licensing review. Check nutrition definitions, bilingual mapping, coverage, and provenance before reuse. Real-time business APIs are outside the design.
- Target a Render Static Site and Web Service with GitHub-driven deployment. Develop on branches, test locally before merging to main, keep the deployment URL stable, and persist database state independently with versioned migrations. Plan database rollback separately from code rollback.
- Use `frontend/`, `backend/`, `supabase/migrations/`, `data/`, `evaluation/`, and `docs/`. The deployment baseline anticipates a future root `render.yaml`.
- Before real user testing, verify service terms, privacy, pricing, and plan limits. Account for cold starts, database sleep, model data handling, API abuse, rate limits, and cost controls.

## Roadmap and validation

| Development day | Goal from the Day 1 baseline |
| --- | --- |
| 1 | PRD, pages, stack, and Assistant design |
| 2 | Development environment, GitHub, and frontend and backend initialization |
| 3 | Minimal end-to-end loop and first public deployment attempt |
| 4 | Nutrition and recipe data, Supabase tables, and permissions |
| 5 | Planning, three ingredient modes, and nutrition calculations |
| 6 | Equal onboarding, profile, pantry snapshots, and bilingual UI |
| 7 | Photo and text logging with confirmation |
| 8 | Replanning, global routing, account persistence, and guest migration |
| 9 | AI evaluation, regression tests, safety, cost, and latency |
| 10 | Fix critical issues, release the MVP, and open real user testing |

Timing is an estimate. The PRD calls for breaking down the Assistant work on Day 2. Sequential confirmation is an option for complex multi-intent requests. See the [decision record](DECISIONS.md) for the current foundation scope.

| Area | Target or measurement |
| --- | --- |
| Constraint satisfaction and replanning | At least 90% each with explicit test denominators. Test safety-critical constraints separately. |
| Nutrition and image recognition | Pass deterministic nutrition unit tests. Use annotated meals to measure recognition, portion, and nutrition error. |
| Assistant routing | Test single and multiple intents, ambiguity, refusals, and write confirmation. Record accuracy and failure types. |
| Latency and cost | Target meal-plan generation within 20 seconds, separating cold starts. Measure per-call and per-user cost. |
| User testing | Target 10–20 participants and measure plan adoption, gather feedback, and document iterations using actual results. |

Release criteria include a working core loop, usable bilingual flows, access and secret checks, clear confirmation and deletion, and verification of privacy terms and model-service suitability.

## Out of scope

Native apps, formal WeChat mini program release, delivery-platform integrations, real-time prices and ordering, precise inventory ledgers and automatic depletion, social features, subscriptions, complex historical health reports, gamification, and general AI chat.

## Open questions

- Assistant task limits, confirmation UX, chat persistence, and whether to include a shopping reference in P0.
- Model version, data licensing and coverage, nutrition safety policy, registration method, and guest migration details.
- Default language, high-fidelity UI, Chinese product name, and WeChat mini program category and eligibility.
- Current free-tier limits, public-test costs, and sensitive-data handling.

## Revision history

| Version | Date | Change |
| --- | --- | --- |
| v1.0 | 2026-11-20 | Original nine requirements, technical direction, and page structure |
| v1.1 | 2026-11-20 | Added FR10, intent routing, and confirmation rules |

Keep the Word baseline and record revised requirements and decisions with version history.
