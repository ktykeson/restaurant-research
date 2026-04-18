# Restaurant Research — No-Website Lead Finder

Find restaurants/cafés/bars/bakeries/takeaways **anywhere in the world** that have no website (or only a social-media link). Built for prospecting; designed to grow into an AI enrichment pipeline (Anthropic SDK, image/menu analysis, generated draft websites).

## What you get per restaurant

`name, maps_link, reason (no_website | social_only), website_uri, address, primary_type, place_id, lat, lng`

Maps link uses the API's `googleMapsUri` (`https://maps.google.com/?cid=…`). The short `maps.app.goo.gl/xxxx` form is **only generated when humans tap "Share" inside the Maps app — the Places API does not expose it**. The CID URL opens the same place card.

## Setup

1. **Create a Google Cloud project** and enable **"Places API (New)"** (the legacy Places API will not work).
2. **Create an API key**, restrict it to the Places API (New). Set a Cloud Console **billing budget alert at $50** (recommended).
3. Copy `.env.example` → `.env` and paste your key:
   ```
   GOOGLE_MAPS_API_KEY=AIza...
   ```
4. Install deps:
   ```
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
5. Run:
   ```
   python app.py
   ```
   Open http://127.0.0.1:5000

The first run seeds four Swiss cantons (ZG, ZH, AG, LU) as saved regions so the original dataset keeps working. Add more via the UI — they persist in `data/cache.sqlite`.

## How to use

1. **Add a region** — type anything geocodable in the "Add a region" box (e.g. `Barcelona, Spain`, `Kyoto`, `Brooklyn NY`, `Kanton Bern`). The backend resolves it via OpenStreetMap and saves a bounding box + polygon. The suggested text-search profiles are auto-ticked based on the country.
2. **Pick text-search profiles** — each profile is a set of localized queries (e.g. Turkish → `Lokanta, Kebapçı, Dönerci…`, Japanese → `居酒屋, ラーメン, 定食…`). Tick whichever languages/cuisines are likely in your regions. You can stack several.
3. **Start with one small region** (a city, not a country) to validate end-to-end — Zug is ~30 cells, ~$5–$10 worst case.
4. **Your region selection + ticked profiles persist** across refreshes and restarts — they're stored in `data/cache.sqlite` via `/api/ui-state`.
5. Watch the live counters. Results stream in as they're found.
6. Click **Download CSV** when done.
7. Re-running with **Use cache** ON costs ~$0 for cells you've already swept — every cell+bucket query is memoized.

## How it works (recall strategy)

The Places API caps searches at 20 results each. To reach *all* restaurants in a region:

1. **Hex-grid decomposition** — each region is tiled with overlapping circles. The grid uses a **per-region azimuthal equidistant projection** centered on the region centroid, so cell spacing is metric-accurate at any latitude (Zürich, Jakarta, Reykjavik).
2. **Type-narrowed buckets** per cell — 6 separate `searchNearby` calls (restaurant core, ethnic restaurants, café/bakery, bar/pub, takeaway/delivery, fast-casual).
3. **Localized text-search supplements** — every ticked profile adds its queries (`Lokanta, Pideci, Dönerci…` for Turkish, etc.) to catch places mis-typed by Google.
4. **Dedup** by `place_id` in SQLite.
5. **Polygon clip** — drop places outside the region polygon (bounding boxes leak across borders).

Field-mask trick: `places.websiteUri` is fetched in the search response — no second Place Details call.

## Profiles

Built-in: English, Swiss-German, German, Italian, French, Spanish, Portuguese, Turkish, Japanese, Chinese, Korean, Arabic, Thai, Vietnamese, Hindi/Indian, Russian, Polish, Dutch. Add more in `search/query_profiles.py`.

Each profile also carries a `suggested_language_code` that becomes the region's default `languageCode` on Places API calls — Google's matcher returns better hits when the language matches the region's natural one.

## Cost

Places API (New) at the Pro tier (which the `websiteUri` field mask requires) is roughly **$32/1k requests**. Cost scales with `cells × (6 nearby buckets + N text queries)`. Examples at default radius 1km:

| Region                 | Cells | Buckets/cell (de_swiss) | Worst-case requests | Worst-case cost |
|------------------------|------:|------------------------:|--------------------:|----------------:|
| Zug (canton)           |   ~30 |                      20 |                ~600 |             ~$20 |
| Zürich (canton)        |  ~860 |                      20 |              ~17000 |            ~$540 |
| Barcelona (city bbox)  |  ~160 |                      22 |               ~3500 |            ~$110 |
| Tokyo 23 wards         | ~2200 |                      18 |              ~40000 | ~$1280 (do NOT) |

Use the **Hard request budget** field to cap spend per run, and **Test mode** (stop each region after N leads) for cheap sanity checks. Untick profiles you don't need to drop buckets-per-cell.

## Project layout

```
app.py                       Flask: routes + SSE stream + CSV download
search/
├── regions.py               Region dataclass + seeding of original cantons
├── query_profiles.py        Localized text-search profiles (toggleable)
├── geocoder.py              Nominatim lookup → bbox + polygon + country code
├── places_client.py         Async Google Places API (New) wrapper
├── grid.py                  Hex-grid generator (per-region AEQD projection)
├── type_buckets.py          Narrow includedTypes for searchNearby
├── crawler.py               Orchestrator with budget guard + progress events
├── filters.py               classify(): no_website / social_only / has_site
├── cache.py                 SQLite: places + regions + ui_state + runs
└── exporter.py              CSV writer
templates/index.html         Frontend
static/{app.js,style.css}    Frontend
scripts/fetch_boundaries.py  Refresh bundled Swiss canton GeoJSONs (optional)
data/
├── cache.sqlite             Persistent cache (places, regions, ui_state, runs)
├── boundaries/*.geojson     Seed polygons for the original 4 cantons
└── runs/run-<id>.csv        Per-run exports
```

## API (local)

- `GET  /api/regions` — list saved regions
- `POST /api/regions` — `{query: "Barcelona, Spain"}` → geocodes + saves
- `PATCH /api/regions/<id>` — edit name / language / region_code / text_profiles
- `DELETE /api/regions/<id>` — remove
- `GET  /api/query-profiles` — list available text-search profiles
- `GET/PUT /api/ui-state` — persisted selection (`{region_ids, text_profiles}`)
- `POST /api/estimate` — pre-run cost estimate
- `POST /api/search` — start a crawl (returns `job_id`)
- `GET  /api/jobs/<id>/stream` — SSE progress stream
- `POST /api/jobs/<id>/cancel` — cancel mid-run
- `GET  /api/jobs/<id>/export` — download CSV
- `GET  /api/leads` — browse the persistent leads library
- `POST /api/leads/<place_id>/review` — mark a lead reviewed
- `GET  /api/runs` — list past runs (optional `?status=done|running|budget_exceeded|user_cancelled|error`, `?limit=`)
- `GET  /api/runs/<run_id>` — single-run detail including `cost_usd` + `duration_s`
- `GET  /api/runs/<run_id>/export` — re-export the leads for a past run's regions as CSV
- `GET  /api/usage/summary` — lifetime totals, 30-day requests timeline, per-region spend, cache-hit rate

## Future: AI enrichment hooks

The `places` cache stores full raw JSON per place. A future `search/enrichment.py` can iterate cached places, fetch reviews/photos via Place Details, and call Claude (`anthropic` SDK) to produce summaries / draft websites — without re-querying the Places API.
