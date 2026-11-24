# MealMind v0.2.0-demo.1

This static portfolio demo offers nine content-reviewed Blind Box suggestions and browser-local meal plans. Recipe quantities and estimates still need cook-through verification. Packaged ingredient and allergen evidence remains unverified. Declaring a dietary restriction suppresses recommendations until it can be verified. See the [content review and provenance](BLIND_BOX_REVIEW.md).

Smart Planning can load a fixed sample explicitly labeled as a demonstration. Nutrition and Replan show examples. Live Gemini, food-log storage and private data tools are available separately in local development. Plans are only available to this browser profile and site origin. There are no accounts, device sync, hosted food logs, or backend in the public demo. Clearing browser storage removes its plans.

## Deploy the static site

Deploy only after the product owner approves the release. Use the reviewed commit as a Render Static Site connected to `jiyinuojiayounie/MealMind` and the approved release branch. Leave Root Directory blank so the build can access the versioned recipe catalog outside `frontend/`. Set `NODE_VERSION=24.22.3` and `SKIP_INSTALL_DEPS=true`, use build command `cd frontend && npm ci && npm run build`, and publish directory `frontend/dist`. Disable Auto-Deploy for manual release control. Use the HTTPS site URL. Leave API and Gemini environment variables out of the static site.

In Redirects/Rewrites, add a **Rewrite** from each of `/today`, `/blind-box`, `/plan`, `/log`, `/profile`, and `/pantry` to `/index.html`. The React router redirects the legacy Pantry path to Today. Scope rewrites to application routes so `/api/*` is missing on the static site. The root path serves the existing index file. Leave `/api` and its subpaths without rules so missing API resources return 404. Use the same rules for any alternative static host. Do not deploy the FastAPI service or forward requests to it for this demo.

After publishing, test direct addresses and refreshes, draw and save locally, check isolation in a fresh browser profile, and confirm that no API or personal data is served. At 375×667 and 390×844, check the wheel, recipe sheet, save confirmation, and local plan history. Read about [Render's static site settings](https://render.com/docs/static-sites).

To run the production build locally, use `cd frontend && npm ci && npm run build && npm run preview`. To exercise the release with an explicit routes-only rewrite and no API, run `node scripts/test_public_demo_browser.mjs` from the repository root after building. The test uses Chrome on macOS and disposable browser profiles.
