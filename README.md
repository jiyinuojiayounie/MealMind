# 🍽️ MealMind

**Less deciding, more eating.**

A bilingual, mobile-first **AI-assisted meal decision assistant** designed to make everyday food choices easier for students and young professionals living independently.

**[Try the live demo](https://mealmind-ao3k.onrender.com/)** · [Product decisions](docs/DECISIONS.md) · [Release notes](docs/PORTFOLIO_RELEASE.md)

> **Current public release: v0.2.1** — an AI meal planner with browser-local Log, Analyze and Replan. The public site includes live Gemini Smart Planning, the Blind Box, saved meal plans, manual food logs, deterministic nutrition estimates, and local replanning.

## Why MealMind?

“**What should I eat today?**” is a surprisingly repetitive decision. Existing diet tools often emphasize tracking and nutritional targets, while the immediate problem is simply choosing something practical and appealing to eat.

MealMind explores a **decision-first** experience: help people pick a meal quickly, let them plan when they have a specific preference, and connect planning with what they actually eat.

**Target users:** Chinese-speaking students and young professionals cooking or choosing meals for themselves. The interface supports Simplified Chinese and English.

## Explore the public demo

1. Open **[MealMind](https://mealmind-ao3k.onrender.com/today)** on mobile or desktop.
2. Select breakfast, lunch, or dinner and spin the **Blind Box**.
3. Explore the suggested meal, ingredients, and cooking steps; redraw if you want another option.
4. Add it to today's plan, or review a replacement before confirming. Refresh the page to see your saved plan again.
5. In **Food Log**, enter the food and any known quantities, save a draft, then confirm what you actually ate.
6. In **Today**, review nutritional coverage for confirmed foods and preview a replacement for an eligible meal. Accept it to create a new plan revision.

The public Blind Box currently contains **9 curated demo meals**. Recipes are selected for content review, but cooking times, portions, packaged ingredients, and allergen evidence are not all independently verified. If an explicitly declared restriction cannot be verified, the demo conservatively withholds a recommendation.

## Feature availability

| Feature | Public portfolio demo | Private local development |
| --- | --- | --- |
| **Meal Blind Box** | Interactive; 9 demo meals, instant redraw | Interactive; larger development candidate pool |
| **Daily meal plan** | Add/replace, explicit confirmation, one current plan and version history; saved in browser IndexedDB | Available with local workflow integration |
| **Natural-language AI planning** | Live Gemini generation with shared request quotas | Gemini integration with a successful isolated browser verification |
| **Food logging** | Manual records, draft and confirmation, browser-local | Local FastAPI/SQLite workflow |
| **Nutrition analysis** | USDA-based estimates from confirmed browser-local logs; partial coverage shown | Deterministic calculations from traceable reference data, with coverage limitations |
| **Adaptive replanning** | Deterministic suggestions from nine local candidates; confirmed and user-locked meals are protected | Local workflow with validation and tests |

**Privacy and storage:** The public demo has no accounts or hosted food-log database. Smart Planning sends the submitted meal request to Google Gemini through the dedicated HTTPS API. Gemini credentials stay on the server. Avoid sensitive personal information in planning prompts. Plans and confirmed food records stay in the current browser for this site. They do not sync between devices, and clearing site data removes them.

## Product decisions and iteration

This project is both a working software prototype and an exercise in **end-to-end AI product development**.

- **Decision-first, not calorie-first.** Prioritized a one-click Blind Box and practical meal suggestions over strict nutritional optimization.
- **Less interface complexity.** Moved the wheel directly onto Today, made result/redraw usable together on mobile, removed duplicate shortcuts, and retired standalone pantry management.
- **Explicit user control.** Drawing a meal does not log it as eaten. Saving and replacing meals are separate, confirmed actions; prior plan versions remain available.
- **Hybrid AI and deterministic logic.** Local recipe selection and plan-storage safeguards do not require a model call; natural-language planning uses a separate Gemini/FastAPI workflow.
- **Transparent uncertainty.** Unverified allergy evidence blocks restricted recommendations, and incomplete nutrition coverage remains visible rather than producing invented precision.

For detailed rationale, review [the decision record](docs/DECISIONS.md), [product requirements](docs/PRD.md), and [recipe review/provenance](docs/BLIND_BOX_REVIEW.md).

## Architecture and technologies

| Layer | Technology | Role |
| --- | --- | --- |
| Frontend | React, TypeScript, Vite, Tailwind CSS, i18next | Mobile-first bilingual interface |
| Public demo persistence | Browser IndexedDB | Local daily plans, revision history, meal locks and food logs |
| Local backend | Python, FastAPI | Meal-generation API, validation, food-workflow services |
| AI integration | Google Gemini API | Natural-language meal planning on the public site and in local development |
| Local food-log persistence | SQLite | Development-only confirmed food logs |
| Content and evaluation | Versioned JSON, Python tests, browser tests | Recipes, reference data, validation, and regression checks |
| Deployment | Render Static Site + Render Free Web Service | Public HTTPS frontend and isolated Gemini planning API |

The project is a monorepo: `frontend/` contains the UI, `backend/` the private/local APIs and application logic, `data/` the recipe and nutrition references, `evaluation/` test evidence, and `docs/` product and engineering notes. The `supabase/migrations/` folder is a placeholder, **not an active public database**.

## Development and technical documentation

The instructions below are retained for developers who want to run or inspect the private/local workflows. They **do not describe capabilities available on the public static demo**.

## Manage local development on macOS

Install the frontend and backend dependencies once using the setup commands below. From the repository root, run:

```sh
./dev start
./dev status
./dev restart
./dev stop
```

`start` launches both services in the background and waits for HTTP readiness. `status` shows managed services and unmanaged port occupants. `restart` rereads `backend/.env` and `frontend/.env.local` by starting fresh processes. `stop` gracefully shuts down only process groups whose local supervisors the tool can verify. Keep the existing environment files in place. The manager does not install dependencies or change food-log data.

Open [MealMind](http://127.0.0.1:5173) or the [FastAPI docs](http://127.0.0.1:8000/docs). Both servers bind only to loopback. FastAPI uses reload and disables proxy headers. To enable development-only backend routes, keep `MEALMIND_ENVIRONMENT=development` in the backend environment or start the manager with `MEALMIND_ENVIRONMENT=development ./dev start`. If supplied only in the shell, pass it again when restarting.

Follow the private, Git-ignored logs with:

```sh
tail -f .dev-local/backend.log .dev-local/frontend.log
```

The logs contain fixed startup, error category, and shutdown messages. Raw application output is withheld to avoid exposing credentials or food-log descriptions. Startup errors point to the relevant log. The manager uses macOS `lsof`, `ps`, and Unix sockets. If it cannot verify a saved supervisor, it leaves the recorded group untouched.

If a port is occupied, read the PID and process name shown by `./dev status` or `./dev start`. Find the owning app or original terminal and close or stop it there before retrying. If you cannot identify the process, leave it running. Do not start manual servers alongside `./dev`.

## Run the frontend locally

For manual startup, start the backend described below first. Use Node.js 24 and npm. From the repository root, run:

```sh
cd frontend
npm ci
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173) or [http://localhost:5173](http://localhost:5173). Vite uses port 5173 and exits if that port is occupied. The development frontend checks the API at `http://127.0.0.1:8000` by default. To use a different backend, set `VITE_API_BASE_URL` in `frontend/.env.local` and restart Vite. The frontend opens in Simplified Chinese on first visit and remembers the selected language in this browser.

From `frontend/`, run `npm run lint` and `npm run build` to check the source and generate the production build.

## Preview the Blind Box on your phone

Use a trusted network and keep FastAPI bound to `127.0.0.1`. Keep the backend running on port 8000, using the existing local development instructions. In a separate terminal, start a second Vite process on a different port so that the regular Mac app remains available:

```sh
MAC_LAN_IP="$(ipconfig getifaddr en0)"
printf '%s\n' "$MAC_LAN_IP"
cd ~/Desktop/MealMind/frontend
VITE_LAN_PREVIEW=1 npm run dev -- --host "$MAC_LAN_IP" --port 5174 --strictPort
```

If the IP is blank, go to **System Settings → Network → Wi‑Fi → Details → TCP/IP**, find the IPv4 address, and set `MAC_LAN_IP` to that address before starting Vite. Open `http://<MAC_LAN_IP>:5174/blind-box` on a phone on the same network, for example `http://192.168.1.42:5174/blind-box`.

In this mode the browser uses relative API paths, and Vite forwards only the read-only health check to the Mac's loopback backend. You can draw, redraw and view recipes on the phone. Adding to a plan, AI generation and private log data are available through the regular loopback app on the Mac. Browser storage is per origin and device. No plan or log data is shared with the phone. If the page is unreachable, check the network address, Mac firewall and whether the Wi-Fi network isolates clients. Stop the LAN preview with Ctrl+C when finished.

## Run the backend locally

Use Python 3.14. Open a separate terminal at the repository root and run:

```sh
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Open the [interactive API documentation](http://127.0.0.1:8000/docs) or check the endpoint directly.

```sh
curl -i http://127.0.0.1:8000/api/v1/health
```

Wait for Uvicorn to log `Application startup complete` before opening the frontend. The expected response is HTTP 200 with `{"service":"mealmind-api","status":"ok"}`. The frontend's development-only indicator checks this endpoint when the app loads and when you retry after a failed request. It reports API reachability.

The backend reloads when Python source changes. Restart it after editing `backend/.env`. Both servers run with defaults. Override backend settings with environment variables or a `backend/.env` file. Set `MEALMIND_CORS_ORIGINS` to a JSON array of exact frontend origins if Vite runs on a different host or port. The defaults allow `http://localhost:5173` and `http://127.0.0.1:5173`.

### Troubleshoot a local connection

Run the health check above first. A connection refusal means nothing is accepting connections at the configured address. If startup reports that port 8000 is in use, inspect the listener and its working directory before stopping it:

```sh
lsof -nP -iTCP:8000 -sTCP:LISTEN
ps -p PID -o pid,ppid,comm
lsof -a -p PID -d cwd
```

Replace `PID` with the listener's numeric process ID. For an old MealMind instance, use Ctrl+C in its original terminal, then start the backend with the reload command above.

If health succeeds but generation fails in the browser, use the exact browser origin in this preflight check. It exercises CORS without invoking Gemini.

```sh
curl -i -X OPTIONS 'http://127.0.0.1:8000/api/v1/meal-plans/generate?infer_scope=true' \
  -H 'Origin: http://127.0.0.1:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

Expect HTTP 200 and an `Access-Control-Allow-Origin` header matching the origin.

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

Invalid input returns HTTP 422. Missing credentials return 503, provider or invalid output errors return 502, and transport timeouts return 504. A generation makes at most two provider attempts, with a single retry only after an upstream HTTP 503. For local troubleshooting, set `MEALMIND_GEMINI_DIAGNOSTICS=true` in `backend/.env` and restart FastAPI to log upstream HTTP codes and sanitized diagnostic summaries. API tests mock Gemini and run without credentials. The endpoint is intended for local development and has no authentication or rate limiting. Check dietary restrictions and allergies before using generated recipes.

## Try catalog-guided planning locally

The existing planner uses prompt-only generation by default. The catalog path requires both a server opt-in and the explicit `planning_mode=catalog` query parameter. The frontend defaults to prompt-only generation, including when the local selector is visible.

For local draft review, add the following to the Git-ignored `backend/.env` file, then start or restart FastAPI on `127.0.0.1` using the local startup command above. Draft requests must use a loopback client and server address. Use direct loopback access and keep draft mode off on deployments.

```dotenv
MEALMIND_ENVIRONMENT=development
MEALMIND_CATALOG_PLANNING_ENABLED=true
MEALMIND_CATALOG_USE_DRAFTS=true
MEALMIND_CATALOG_PERSONALIZATION=false
```

Smart Planning uses Gemini in private local development. For developer-only catalog testing, send the same request body directly to `POST /api/v1/meal-plans/generate?planning_mode=catalog` on the loopback backend. Keep catalog personalization disabled for deterministic local review. Catalog Replan can be exercised through the local preview API or backend tests.

Edit the local env files in place to preserve the API key and any other values. Before starting either server, stop any existing MealMind instance from its original terminal. The [backend command](#run-the-backend-locally) binds FastAPI to `127.0.0.1:8000` with reload. The [frontend command](#run-the-frontend-locally) uses Vite on port 5173. Server-side development and loopback checks still control draft access.

Try an explicit single dinner with known ingredients. This call is deterministic with the settings above and requires no Gemini key.

```sh
curl -i 'http://127.0.0.1:8000/api/v1/meal-plans/generate?planning_mode=catalog' \
  -H 'Content-Type: application/json' \
  -d '{
    "user_request": "Plan dinner",
    "language": "en-US",
    "scope": "single_meal",
    "ingredient_mode": "existing",
    "available_ingredients": ["cooked rice", "eggs", "bok choy", "cooking oil", "salt"],
    "cooking_time_limit": 16
  }'
```

This request returns the draft egg and bok choy fried rice with a 16-minute catalog estimate and an empty additional-ingredient list. Successful responses use the existing meal-plan schema. The response marks draft portions and times as unverified. Independent nutritional adequacy and allergen safety are outside this preview.

When the opt-in is disabled or draft access is forbidden, the endpoint returns 403. Unresolved requests and unsupported constraints return 422 with a structured status and reason codes. An empty feasible set returns 409 with `no_feasible_plan`. Production catalog retrieval uses reviewed records only. The bundled catalog has zero reviewed entries.

Optional `MEALMIND_CATALOG_PERSONALIZATION=true` uses the existing Gemini credentials. It may make one provider call if at least two eligible plans exist. The model sees catalog candidate summaries and a cuisine preference when present. It can select only a supplied candidate ID and a fixed explanation reason. The backend resolves the ID to the exact validated plan and builds the response from catalog data. An invalid choice returns 502. The catalog path has no prompt-only fallback.

## Working in this repository

Read the [product requirements](docs/PRD.md), [architecture and development conventions](AGENTS.md), and [decision record](docs/DECISIONS.md) before changing the project. See the [changelog](CHANGELOG.md) for completed work. The [original Word PRD](docs/MealMind_PRD_v1.1.docx) is preserved alongside the Markdown baseline.

The [environment template](.env.example) documents local overrides and reserved integration settings.

### Local food log API

The food log endpoints are available only in local development. See the [food log API guide](docs/FOOD_LOGS.md) for the loopback startup command, draft and confirmation requests, and storage migration notes.

The opt-in v0.2.1 planner deployment and its activation gates are documented in [Public AI Planning Release](docs/PUBLIC_AI_PLANNING_RELEASE.md).
