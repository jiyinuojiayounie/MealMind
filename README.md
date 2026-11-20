# MealMind

MealMind is a mobile-first, Simplified Chinese and English meal planning assistant for Chinese-speaking students and young professionals living independently. It starts with Chinese food and connects planning, meal logging, nutrition analysis, and replanning.

## Project status

The Day 2 frontend runs locally with bilingual navigation and feature previews. The backend and service integrations are pending.

| Directory | Purpose |
| --- | --- |
| `frontend/` | React, TypeScript, Vite, Tailwind CSS, and i18next for the web UI |
| `backend/` | Python and FastAPI modular monolith for REST, business rules, and AI integration |
| `supabase/migrations/` | Versioned migrations for Supabase PostgreSQL and access policies |
| `data/` | Future nutrition and recipe reference data with documented provenance and licensing |
| `evaluation/` | Future AI evaluation cases, scoring, and reports |
| `docs/` | Product requirements and decision history |

Supabase Auth is the planned authentication service. Gemini is the initial multimodal model candidate. The deployment target is Render, with a Static Site for the frontend and a Web Service for the backend.

## Run the frontend locally

Use Node.js 24 and npm. From the repository root, run:

```sh
cd frontend
npm ci
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) or the URL printed by Vite. Local development requires no environment variables. The frontend opens in Simplified Chinese on first visit and remembers the selected language in this browser.

From `frontend/`, run `npm run lint` and `npm run build` to check the source and generate the production build.

## Working in this repository

Read the [product requirements](docs/PRD.md), [architecture and development conventions](AGENTS.md), and [decision record](docs/DECISIONS.md) before changing the project. See the [changelog](CHANGELOG.md) for completed work. The [original Word PRD](docs/MealMind_PRD_v1.1.docx) is preserved alongside the Markdown baseline.

The [environment template](.env.example) documents proposed configuration names.
