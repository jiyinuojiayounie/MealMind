# MealMind

MealMind is a mobile-first, Simplified Chinese and English meal planning assistant for Chinese-speaking students and young professionals living independently. It starts with Chinese food and connects planning, meal logging, nutrition analysis, and replanning.

## Project status

The Day 2 frontend runs locally with bilingual navigation and feature previews. The FastAPI backend serves a health endpoint used by the frontend in development. Business features and external service integrations are pending.

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

Open [http://localhost:5173](http://localhost:5173) or the URL printed by Vite. The development frontend checks the API at `http://127.0.0.1:8000` by default. To use a different backend, set `VITE_API_BASE_URL` in `frontend/.env.local` and restart Vite. The frontend opens in Simplified Chinese on first visit and remembers the selected language in this browser.

From `frontend/`, run `npm run lint` and `npm run build` to check the source and generate the production build.

## Run the backend locally

Use Python 3.14. Open a separate terminal at the repository root and run:

```sh
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open the [interactive API documentation](http://127.0.0.1:8000/docs) or check the endpoint directly.

```sh
curl -i http://127.0.0.1:8000/api/v1/health
```

The expected response is HTTP 200 with `{"service":"mealmind-api","status":"ok"}`. The frontend's development-only indicator checks this endpoint when the app loads and when you retry after a failed request. It reports API reachability.

Both servers run with defaults. Override backend settings with environment variables or a `backend/.env` file. Set `MEALMIND_CORS_ORIGINS` to a JSON array of exact frontend origins if Vite runs on a different host or port. The defaults allow `http://localhost:5173` and `http://127.0.0.1:5173`.

From `backend/`, run `.venv/bin/python -m pytest` to test the API.

## Working in this repository

Read the [product requirements](docs/PRD.md), [architecture and development conventions](AGENTS.md), and [decision record](docs/DECISIONS.md) before changing the project. See the [changelog](CHANGELOG.md) for completed work. The [original Word PRD](docs/MealMind_PRD_v1.1.docx) is preserved alongside the Markdown baseline.

The [environment template](.env.example) documents local overrides and reserved integration settings.
