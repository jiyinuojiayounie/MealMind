# Local food log API

The API is a single-user development tool. Production does not register these routes. Run it directly over loopback with proxy headers disabled. Do not forward it via a reverse proxy, tunnel, or shared development server. The API checks the peer and listener addresses, the Host header, and browser Origin when supplied. These checks do not identify individual local users or processes. SQLite data is stored in plaintext with restrictive permissions for newly created files.

From the repository root with the existing backend virtual environment installed:

```sh
cd backend
MEALMIND_ENVIRONMENT=development .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
```

By default the database is created on first use at `backend/.local/food-logs.sqlite3`. `MEALMIND_FOOD_LOG_DB_PATH` can override it. Use a private directory and an ignored database extension. SQLite uses `PRAGMA user_version` and the ordered migration statements in `app/storage/food_logs.py`. Migrations run in a write transaction, and an older application refuses a newer database. Before applying future migrations to data you need to keep, back up the database with SQLite's backup API or stop writers before taking a filesystem backup. Keep released migrations immutable and test upgrades on a copy.

| Method and path | Behavior |
| --- | --- |
| `POST /api/v1/food-logs` | Create a draft and return 201. The server supplies ID, status, revision, and timestamps. |
| `GET /api/v1/food-logs?date=2026-11-21` | List drafts and confirmed logs by the calendar date of the recorded offset. Sort by consumption instant and ID. |
| `PUT /api/v1/food-logs/{id}` | Replace draft content. Supply the revised description, items, consumption timestamp, meal type (or omit for unspecified), and `expected_revision`. Source is immutable. |
| `POST /api/v1/food-logs/{id}/confirm` | Send `{"expected_revision": 1}` for the revision reviewed by the user. A retry of the same confirmation returns the confirmed record without updating it again. |
| `DELETE /api/v1/food-logs/{id}?expected_revision=2` | Explicitly delete a draft or confirmed record and return 204. Absent records return 404. Stale revisions return 409. |

Example draft payload:

```json
{
  "meal_type": "breakfast",
  "consumed_at": "2026-11-21T08:30:00+08:00",
  "description": "Steamed egg with rice",
  "items": [
    {"name": "Steamed egg", "preparation_method": "steamed", "quantity": null},
    {"name": "Rice", "quantity": 1, "unit": "bowl"}
  ],
  "source": "manual_text"
}
```

Quantities can be unknown. Only confirmed records are eligible for future nutrition summaries. The API does not calculate nutrition or connect to meal planning. The persistence routes perform no recognition.

For a public MVP, use private browser-local persistence for guests per FR08, or require a scoped, authenticated owner for server records. An authenticated PostgreSQL implementation needs versioned migrations, owner-scoped queries and Supabase RLS, and tests for owner isolation, explicit confirmation, and deletion. Preserve UUIDs, original UTC offsets or recorded local dates, source, draft status, unknown quantities, and timestamps in any authorized import. SQLite data must never be uploaded automatically. Guest-to-account migration requires explicit consent and retry-safe writes.

## Local Log page

With the loopback API running, start Vite in another terminal:

```sh
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173/log`. The page uses the default API at `http://127.0.0.1:8000` unless `VITE_API_BASE_URL` overrides it. It accepts only loopback frontend and API URLs in Vite development mode. Production builds show an unavailable state. Use the existing server if either port is already in use.

Enter a description and manually add at least one food item. Save the draft, then review its card before confirming. A stale revision triggers a list refresh and keeps unsaved corrections visible. Review the latest draft before applying changes again. A failed creation is never retried automatically. Check the consumption date for an existing draft before retrying a save whose outcome could not be verified.

New or adjusted times use the browser timezone's offset at the chosen date and time. An unchanged draft time retains its recorded offset. Local times skipped by daylight-saving changes are rejected. Repeated wall times use the browser's earlier offset. The date filter uses the recorded calendar date.

## Text recognition preview

`POST /api/v1/food-logs/recognize-text` accepts `{"description": "..."}` with up to 2,000 characters of Chinese, English, or mixed text. It uses the existing server-side Gemini API key and model settings and shares the food log loopback access checks. Calling this endpoint sends the description to Gemini. Use fictional descriptions for development tests.

The endpoint returns an unsaved draft proposal with `description`, `source: "ai_text"`, `status: "draft"`, `items`, and `notes`. It never opens the log database. Names, preparation methods and portion phrases must match quotes from the description. A narrow parser handles common explicit portions such as `150g`, `半碗`, and `一小把`, preserving the original unit. Ambiguous or unsupported portions remain unknown. Review each suggestion before saving, including whether the model attributed a quote to the right food. An empty items list is a valid proposal when there is no identifiable food.

Items may include `quantity_unspecified` or `portion_needs_review` as a `portion_note`. The proposal can include `no_identifiable_foods` and `description_needs_review` in `notes`. Before saving through the separate persistence API, the client must let the user review and correct items, strip proposal-only notes, and collect the actual consumption timestamp. Confirmation remains a separate user action. In the local Log page, enter a description and select **Recognize with AI** to request a proposal. Empty item fields can be populated immediately. Existing entries are kept until you explicitly choose to replace them. If you change the description, review any applied items against it or run recognition again. Saving a new AI-assisted draft records `ai_text` as its source. Correcting an existing draft preserves its original source. Manual entry remains available.

## Image recognition preview

`POST /api/v1/food-logs/recognize-image` accepts one multipart file in the `image` field:

```sh
curl --fail-with-body -F 'image=@fictional-meal.jpg' http://127.0.0.1:8000/api/v1/food-logs/recognize-image
```

The route is available only on the development loopback backend. It accepts still JPEG, PNG, and WebP files. The file limit is 5 MiB. The original image can be up to 8,192 pixels on either side and 24 megapixels. The server checks the image bytes, applies EXIF orientation, and creates a metadata-free JPEG with a longest side of at most 1,600 pixels. Only that JPEG is sent to Gemini. The server processes the upload in memory and does not retain the original or normalized photo. Do not include sensitive material in photos sent to the provider.

A successful response is an unsaved draft proposal with `source: "ai_image"`, `description: null`, and editable item fields. There may be a tentative count for visually distinct pieces. Weights and nutrition values are outside this contract. Review `identity_uncertain` and `portion_note` before reusing any item. If nothing is recognized, the response contains an empty list and `no_identifiable_foods`. The user must supply an actual description and consumption time, remove proposal-only fields from items, and separately save and confirm the log. In the local Log page, use the standard **Meal photo** picker to preview an image. Select **Recognize photo with AI** to send it to Gemini. You can replace or remove the photo during recognition. Existing items remain until you explicitly choose to replace them. The browser keeps the photo and its preview only in memory. An applied image proposal gives a new draft the `ai_image` source. Editing a saved draft preserves its existing source.
