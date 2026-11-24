# MealMind MVP owner guide

## What a first-time user can do

Open MealMind and choose either onboarding option. On Plan, describe the meal, optionally set limits under More options, and save a suggestion when ready. Select the intended date in Saved plans first. Writing “tomorrow” guides generation but does not set that storage date. On Log, record what you actually ate, save the draft, and explicitly confirm it. Today sums supported entries from confirmed logs and shows unavailable portions and partial coverage. To Replan, pick an unlocked remaining meal on Today's date, review restrictions, then preview and explicitly accept. The original accepted plan remains viewable.

The browser holds accepted plans and revisions in its own local database. The local backend keeps food logs in SQLite. An accepted plan never creates a food log. A replan preview never changes a log or saves a plan. These private workflows are available on development loopback only. No sign-in or shared production storage is required for this UAT.

## Who decides what

| Step | Gemini's role | Rule-based checks |
|---|---|---|
| Original AI Planning | Suggest meals and instructions | Read explicit scope and supported timing constraints, parse the result, enforce slot, time and inventory rules, then record soft meal quality signals and block detected dietary conflicts |
| Catalog Planning | Optional choice among already eligible plans when personalization is enabled | Filter and rank recipes by constraints, practicality and diversity. Rebuild any selected candidate from the catalog. Local drafts are unverified. |
| Text or photo recognition | Suggest foods from quotes or visible evidence on an explicit button click | Check quotes, units and context. Keep cooking-only evidence outside consumption. Recognition never confirms a record. |
| Daily Nutrition | No provider call | Check confirmed logs, valid references, portions and coverage, then calculate against the versioned reference data |
| Replan | Original AI mode suggests one meal; catalog Replan has personalization disabled | Check locked slots and input limitations, then verify food-log fingerprint and browser plan revision before accepting |

## Prompt inventory

| Prompt | Location |
|---|---|
| Original generation and automatic full-day instructions | [app/prompts/meal_plans.py](../backend/app/prompts/meal_plans.py) |
| Single-meal Replan instruction and limited variety context | [app/services/meal_plans.py](../backend/app/services/meal_plans.py), reused from Replan |
| Optional catalog candidate choice | [app/services/catalog_planning.py](../backend/app/services/catalog_planning.py) |
| Food text and image recognition | [app/prompts/food_recognition.py](../backend/app/prompts/food_recognition.py) |

Prompt text is tracked by Git. Original AI traces also show the first 12 characters of a SHA-256 fingerprint of the actual assembled system instructions, including per-request instructions. The configured Gemini model appears separately. A rejection gives a friendly error. The Original AI Planning API makes one additional attempt after a 500 ms delay only when Gemini returns HTTP 503. If Gemini returns 503 again, the API returns 503 and the page says the service is temporarily unavailable. Other provider errors and rejected responses get no automatic retry. The selected mode and model stay in effect.

## Check an unexpected Planning error

Enable `MEALMIND_GEMINI_DIAGNOSTICS=true` on the development backend for the isolated run below. In the browser's Network tab, select the `generate` request and look for the `X-Request-ID` response header. Open `http://127.0.0.1:8001/api/v1/meal-plans/local-traces` and find that ID. The newest 30 traces are held in memory for the original AI generation route.

- `configuration` means generation stopped before the provider call. `provider_http`, `provider_transport` and `provider_timeout` describe provider-stage failures. Provider HTTP details are reduced to fixed messages. `provider_attempts` counts the calls made, and `provider_retry_status` records the first 503 when a retry was scheduled.
- `constraint_verification` indicates that an explicit restriction or time limit could not be verified before contacting Gemini.
- `response_schema` means the response failed the structured parser. `scope_validation`, `time_validation` and `inventory_validation` identify which rule blocked a parsed plan.
- `quality_validation` means that a blocking quality check failed. The trace includes `quality_issues`, `blocking_quality_issues`, and any missing components by meal slot. Free Recommendation can reach `accepted` with soft quality findings. `accepted` means the backend returned a plan. Check the browser response if the UI still fails to render it.
- Browser form validation or a malformed API request may stop before a trace is created. Use the form message and HTTP status in that case.

Traces hold no original description, raw prompt, model reply, credential or food record. Restarting the backend clears them. The trace endpoint is off by default and unavailable outside local development. For inspecting a rendered prompt and raw response, use the fixed-sample live probe below. It can print those details to your terminal on explicit request and writes no capture file. It cannot recover an earlier user's response.

## Isolated owner test

Keep the existing app running on its usual ports if needed. These commands use ports 8001 and 5174. Run from the MealMind repository root. The CLI smoke below assumes Chrome on macOS.

1. In terminal A, create a new test directory and start the backend against its own SQLite file.

   ```sh
   S0_DIR=$(mktemp -d /tmp/mealmind-uat.XXXXXX)
   echo "$S0_DIR"
   (cd backend && MEALMIND_ENVIRONMENT=development MEALMIND_GEMINI_DIAGNOSTICS=true \
     MEALMIND_FOOD_LOG_DB_PATH="$S0_DIR/food-logs.sqlite3" \
     MEALMIND_CATALOG_PLANNING_ENABLED=true MEALMIND_CATALOG_USE_DRAFTS=true \
     MEALMIND_CATALOG_PERSONALIZATION=false \
     MEALMIND_CORS_ORIGINS='["http://127.0.0.1:5174"]' \
     .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001)
   ```

2. In terminal B, start the test frontend, then open `http://127.0.0.1:5174` in a new Chrome profile reserved for this test. Browser storage is also isolated by port. Confirm `http://127.0.0.1:8001/api/v1/health` shows `"status":"ok"`.

   ```sh
   cd frontend
   VITE_API_BASE_URL=http://127.0.0.1:8001 npm run dev -- --port 5174 --strictPort
   ```

3. Start from Welcome and choose **Get started directly**. To prepare a plan without contacting Gemini, draw and explicitly save a Blind Box lunch for today. Refresh and confirm version 1 is present. Submit a Smart Planning request only when ready to use the provider.
4. Open Log. Manually record **熟长粒糙米, 150 g**, for lunch today. Save the draft and confirm that Today still excludes it. Then confirm actual consumption and check Today shows **1/1** calculated items and a lunch lock.
5. In Today's Replan card, select dinner and review restriction status. Use the mock-backed browser regression below for a provider-free walkthrough. For an authorized manual Gemini session, generate a preview, then explicitly accept it or keep the current plan. After accepting, refresh and check that version 2 changes dinner only, the original plan is still visible, and confirmed lunch remains locked.
6. Stop the two test terminals with Ctrl+C. For a clean rerun use a new temporary directory and a fresh test Chrome profile. No reset of normal SQLite, IndexedDB or browser data is needed.

## Verification entry points

- **Offline browser smoke** from the repository root with `node scripts/test_food_binding_browser.mjs`. This builds the development-enabled frontend, starts FastAPI on separate ports, mocks the provider behind the shared validator, and uses a temporary Chrome profile and SQLite. It tests both planning modes, a generation rejection, meal plan acceptance, Lunch Log and Today, and Replan with version preservation.
- **Single live attempt**, only when authorized to use the configured Google project. From `backend/`, run `.venv/bin/python -m scripts.smoke_live_planning --live`. This sends only the fixed sample request, uses the same generation and validation service as the endpoint, and writes no logs or saved plans. Add `--show` to display the rendered system prompt, fixed synthetic request, and returned raw response if available. One invocation makes at most one attempt. Check quota and billing for your own project before running. There is no need to repeat the command to diagnose a recorded stage.

## Constraint audit

| Category | Current examples |
|---|---|
| Hard safety or explicit setting | Catalog allergen evidence, verified strict dietary requirements, explicit inventory and time limits, locked Replan slots, food-log and accepted-plan revision checks, finite positive quantities. Keep any declared restriction user-reviewed. Original AI alone cannot certify allergy safety. |
| Soft quality preference | “Breakfast preferably within 10 minutes”, familiar Chinese home cooking, reduced cleanup, variation in ingredients and cooking style, convenience and ordinary single-person portions. Catalog availability may limit these. |
| Heuristic rule that can reject a reasonable plan | Role lookup uses a limited bilingual name list and can miss mixed dishes or aliases. Trace quantities, per-ingredient size and count thresholds, repeated cooking signatures, and multi-dish breakfast estimates can all misclassify workable suggestions. Estimated times are also model or draft claims. |

For a later iteration, consider a user-triggered review only for an otherwise valid result rejected by a named heuristic. Limit it to the failed role or preparation decision and show it as a proposal. Revalidate scope, time, inventory, dietary restrictions and locks after any change. Measure false rejections and extra calls in offline fixtures before enabling it. This phase includes no AI repair or fallback.


### Live acceptance for Free Recommendation

After product-owner authorization, use the isolated browser setup above with the configured real Gemini provider. In Original AI mode, leave the advanced options at their defaults and submit `帮我生成今天的一日三餐` once. In the Network tab, verify that the Planning POST returned HTTP 200 and capture its `X-Request-ID`. Match the ID to an `accepted` trace with `full_day_required: true` and breakfast, lunch and dinner in `returned_slots`. Compare the dish names and steps in the response to the three rendered sections. Do not save the result. One browser submission can call the provider twice only if the first result is HTTP 503. Record any failure stage before stopping. The service-level probe above does not exercise the browser's Free Recommendation route.
