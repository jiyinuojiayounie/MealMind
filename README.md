# MealMind

MealMind is a mobile-first, Simplified Chinese and English meal planning assistant for Chinese-speaking students and young professionals living independently. It starts with Chinese food and connects planning, meal logging, nutrition analysis, and replanning.

## Project status

The frontend runs locally with bilingual navigation and feature previews. FastAPI serves health checks and a Gemini-backed meal planning endpoint. The frontend checks API reachability in development and generates meal plans when requested from Today → Meal planning.

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

## Generate a meal plan

With both servers running, open Today → Meal planning. Enter your requirements and select **Generate meal plan** to send a request to Gemini through FastAPI.

Set `GEMINI_API_KEY` in the Git-ignored `backend/.env` file and restart FastAPI. Optionally override `GEMINI_MODEL`. The default, `gemini-3.1-flash-lite`, supports structured output and is listed for standard text generation on Google's [free tier](https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite). Eligibility and quotas depend on the Google project. This app does not change billing settings.

```sh
curl -fsS http://127.0.0.1:8000/api/v1/meal-plans/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "user_request": "Make a simple Chinese-style dinner with tomatoes and eggs.",
    "language": "en-US",
    "scope": "single_meal",
    "meal_type": "dinner",
    "available_ingredients": ["tomatoes", "eggs", "water", "salt"],
    "ingredient_mode": "existing",
    "cooking_time_limit": 20
  }'
```

The response contains a title, meals with dishes and approximate ingredient quantities and units, cooking instructions, estimated preparation minutes per meal, an explanation, and any additional ingredients. `meal_type` is optional for `single_meal` and must be omitted or null for `full_day`. For a full day, the time limit applies to each meal. Existing mode requires an ingredient list and rejects unlisted structured ingredients, including unlisted staples. Available ingredient labels are preserved across languages so the backend can compare them against the request.

Invalid input returns HTTP 422. Missing credentials return 503, provider or invalid output errors return 502, and transport timeouts return 504. Each generation makes at most one provider attempt. For local troubleshooting, set `MEALMIND_GEMINI_DIAGNOSTICS=true` in `backend/.env` and restart FastAPI to log upstream HTTP codes and sanitized diagnostic summaries. API tests mock Gemini and run without credentials. The endpoint is intended for local development and has no authentication or rate limiting. Check dietary restrictions and allergies before using generated recipes.

## Working in this repository

Read the [product requirements](docs/PRD.md), [architecture and development conventions](AGENTS.md), and [decision record](docs/DECISIONS.md) before changing the project. See the [changelog](CHANGELOG.md) for completed work. The [original Word PRD](docs/MealMind_PRD_v1.1.docx) is preserved alongside the Markdown baseline.

The [environment template](.env.example) documents local overrides and reserved integration settings.
