# MealMind

MealMind is a mobile-first, Simplified Chinese and English meal planning assistant for Chinese-speaking students and young professionals living independently. It starts with Chinese food and connects planning, meal logging, nutrition analysis, and replanning.

## Project status

Day 2 establishes the repository structure and documentation. The frontend and backend have no runnable applications yet.

| Directory | Purpose |
| --- | --- |
| `frontend/` | React, TypeScript, Vite, Tailwind CSS, and i18next for the web UI |
| `backend/` | Python and FastAPI modular monolith for REST, business rules, and AI integration |
| `supabase/migrations/` | Versioned migrations for Supabase PostgreSQL and access policies |
| `data/` | Future nutrition and recipe reference data with documented provenance and licensing |
| `evaluation/` | Future AI evaluation cases, scoring, and reports |
| `docs/` | Product requirements and decision history |

Supabase Auth is the planned authentication service. Gemini is the initial multimodal model candidate. The deployment target is Render, with a Static Site for the frontend and a Web Service for the backend.

## Working in this repository

Read the [product requirements](docs/PRD.md), [architecture and development conventions](AGENTS.md), and [decision record](docs/DECISIONS.md) before changing the project. See the [changelog](CHANGELOG.md) for completed work. The [original Word PRD](docs/MealMind_PRD_v1.1.docx) is preserved alongside the Markdown baseline.

The [environment template](.env.example) documents proposed configuration names. No environment configuration is needed to review this foundation. From the repository root, run `git status --short --untracked-files=all` to list the foundation files before staging.
