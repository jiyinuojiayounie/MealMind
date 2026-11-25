# MealMind v0.2.1

The browser-local public release includes the nine-meal Blind Box, meal-plan history, manual food logging, deterministic nutrition with coverage, and local replanning. A meal is counted as eaten after explicit log confirmation. Replanning preserves consumed and locked slots. Smart Planning on the static site remains a labeled sample.

The website stays on the existing Render Static Site. Browser-local records remain isolated by site origin and profile. The additive IndexedDB upgrade preserves existing meal plans and history. Real Gemini planning is gated separately and has been verified in an isolated browser. See [Public AI Planning Release](PUBLIC_AI_PLANNING_RELEASE.md) for readiness and rollout.

## v0.2.0-demo.1 baseline and hosting

The initial static portfolio demo offered nine content-reviewed Blind Box suggestions and browser-local meal plans. Recipe quantities and estimates still need cook-through verification. Packaged ingredient and allergen evidence remains unverified. Declaring a dietary restriction suppresses recommendations until it can be verified. See the [content review and provenance](BLIND_BOX_REVIEW.md).

At the initial release, Smart Planning, Nutrition and Replan showed labeled demonstration content. Live Gemini, food-log storage and private data tools are available separately in local development. Plans are only available to this browser profile and site origin. There are no accounts, device sync, hosted food logs, or backend in the public demo. Clearing browser storage removes its plans.

## Deploy the static site

Deploy only after the product owner approves the release. Use the reviewed commit as a Render Static Site connected to `jiyinuojiayounie/MealMind` and the approved release branch. Leave Root Directory blank so the build can access the versioned recipe catalog outside `frontend/`. Set `NODE_VERSION=24.22.3` and `SKIP_INSTALL_DEPS=true`, use build command `cd frontend && npm ci && npm run build`, and publish directory `frontend/dist`. Disable Auto-Deploy for manual release control. Use the HTTPS site URL. Leave API and Gemini environment variables out of the static site.

In Redirects/Rewrites, add a **Rewrite** from each of `/today`, `/blind-box`, `/plan`, `/log`, `/profile`, and `/pantry` to `/index.html`. The React router redirects the legacy Pantry path to Today. Scope rewrites to application routes so `/api/*` is missing on the static site. The root path serves the existing index file. Leave `/api` and its subpaths without rules. Render returned 404 for GET and an empty 200 for POST to nonexistent paths, including the control path. Acceptance requires that no functional private API be available. Use the same rules for any alternative static host. Do not deploy the FastAPI service or forward requests to it for this demo.

After publishing, test direct addresses and refreshes, draw and save locally, check isolation in a fresh browser profile, and confirm that no API or personal data is served. At 375×667 and 390×844, check the wheel, recipe sheet, save confirmation, and local plan history. Read about [Render's static site settings](https://render.com/docs/static-sites).

To run the production build locally, use `cd frontend && npm ci && npm run build && npm run preview`. To exercise the release with an explicit routes-only rewrite and no API, run `node scripts/test_public_demo_browser.mjs` from the repository root after building. The test uses Chrome on macOS and disposable browser profiles.
