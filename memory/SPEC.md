# AgriGaurd — living spec

AI-powered satellite agricultural flood monitoring, land suitability and crop intelligence
platform. FastAPI + MongoDB backend, Vite/React 19 + Tailwind v4 + Leaflet frontend.

## Auth & roles
JWT (httpOnly cookie + Bearer). Roles: FARMER (default), ADMIN, RESEARCHER.
`/api/auth/register|login|logout|me`. Users only ever see their own fields, analyses,
notifications and reports; `/api/admin/*` is ADMIN-only (403 otherwise).
Working logins: see `memory/test_credentials.md`.

## Data model (Mongo)
- `users`: id, email, name, role, password_hash, created_at
- `fields`: id, user_id, name, state/district/village, latitude, longitude, boundary{coordinates},
  bbox, area_ha, flood_status, flood_pct, flood_confidence, land_suitability,
  recommended_crop, monitoring{enabled,frequency}, last_analysis
- `analyses`: id, user_id, field_id, type, boundary, discovery, flood, water, landcover, terrain,
  soil, weather, ndvi, ndmi, land_suitability, crops, evidence, data_quality, state, created_at
- `analysis_jobs`: job_id, user_id, field_id, state (QUEUED→…→COMPLETED/PARTIAL/FAILED),
  stages{}, analysis_id, result_summary
- `notifications`, `audit_log`, `cache` (external-API responses with TTL)

## Key flows
1. Register/login → `/app/dashboard` (field counts, trends, all-fields map).
2. `/app/analyze`: draw polygon/rectangle (Leaflet Draw) or search a place (Nominatim),
   optionally save as field → `POST /api/analyze` returns job_id → frontend polls
   `GET /api/analysis/jobs/{id}` and renders the stage tracker → redirects to
   `/app/analyses/{id}`.
3. Analysis result page: flood, water split, land cover, soil, terrain, weather, NDVI/NDMI,
   land suitability factor breakdown, crop recommendations with reasons, evidence,
   data-quality score. PDF / CSV / JSON export.
4. Fields list + field detail (tabs, history, timeline, comparison, monitoring config,
   Run scan now), notifications, crop library, system health, admin panel, Seed AI.

## Pipeline (services/analysis_service.py)
validate boundary → satellite discovery (Sentinel Hub if credentials) → SAR flood detection →
permanent/seasonal water + river/built-up verification (OSM/Overpass) → land cover →
Copernicus DEM terrain → SoilGrids → Open-Meteo weather → flood confidence (weighted) →
severity → land suitability → crop engine → data quality → save.

## Added features (v2)
- **Sowing calendar** — `GET /api/fields/{id}/sowing-calendar`
  (`services/sowing_service.py`). Per recommended crop, a 12-month grid of
  SOW NOW / SOW / PREPARE / WAIT / UNCERTAIN / AVOID built from ICAR/FAO season
  calendars + the field's crop score + measured Open-Meteo rainfall + detected flood
  severity vs the crop's flood tolerance, with a drainage wait in days. Field tab "Sowing".
- **Village Compare** — `GET /api/fields/{id}/village-compare?radius_km=`
  (`services/village_service.py`). Benchmarks flood % and land suitability against all
  analysed fields within the radius (default 25 km, max 200). Other users' fields are
  ANONYMISED (distance/area/scores only, no owner, name, id or boundary). Needs ≥2
  analysed neighbours, otherwise returns `INSUFFICIENT DATA`. Field tab "Village".
- **Daily flood alerts** — platform cron `.emergent/crons.yml` →
  `POST /api/cron/daily-flood-check` (bearer `WEBHOOK_CRON_SECRET`, acks immediately and
  backgrounds `services/daily_alert_service.py`). Re-analyses every enabled monitoring
  config, flags a ≥1 pp rise in agricultural flood as new water, writes the in-app alert
  and sends one digest email per user via Emergent-managed Resend (`backend/emailer.py`,
  guardrail gate `_assert_safe_email` on every send). SMS is optional via Twilio
  (`backend/sms.py`). Preferences UI (channels, address/phone, min severity, test send)
  lives on the Notifications page; `POST /api/alerts/test` sends a test email.

## Data honesty rules
No fabricated values anywhere. Missing sources render as `DATA UNAVAILABLE`, the job ends in
`PARTIAL`, and the data-quality panel lists exactly which datasets were missing.
Sentinel Hub credentials are NOT configured in this pod, so Sentinel-1/2 derived metrics
(SAR change, NDVI/NDMI, optical confirmation) report DATA UNAVAILABLE and every analysis is
PARTIAL; soil/terrain/weather/crop/suitability are real API results. A separate opt-in
"Demo mode" checkbox runs a prepared sample dataset, always labelled as demo.
Add `SENTINEL_HUB_CLIENT_ID` / `SENTINEL_HUB_CLIENT_SECRET` to `backend/.env` to enable
real satellite analysis.
