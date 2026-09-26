# VajraNet

**India Atmospheric & Disaster Intelligence**

Production-oriented Django platform for monitoring weather, thunderstorm risk estimates, rainfall, temperature, alerts, and disaster preparedness across India.

> Situational awareness only — does **not** replace official IMD / NDMA / state authority warnings.

## 1. Overview

VajraNet provides:

- City search and current weather (Open-Meteo)
- Hourly (24h) and daily (7-day) forecasts
- India-focused Leaflet map with layer toggles
- Baseline thunderstorm nowcasting (explainable rule engine)
- Derived weather alerts (clearly labeled model estimates)
- Lightning page with honest “unavailable” state when no legal feed is configured
- Rainfall & temperature monitoring pages
- Safety center + client-side emergency kit checklist
- Citizen vs Monitoring views
- DRF JSON APIs
- Render-ready deployment

## 2. Architecture

```
views / API → services → providers (external APIs)
                     ↘ Django ORM / cache
```

Apps:

| App | Responsibility |
| --- | --- |
| `weather` | Locations, observations, forecasts, alerts, providers, nowcasting |
| `disasters` | Hazard types, USGS earthquakes, FIRMS stub |
| `safety` | Guidelines + emergency kit |
| `dashboard` | HTML pages |

## 3. Technology stack

- Python 3.12+ / Django 5 / Django REST Framework
- SQLite (dev) → PostgreSQL via `DATABASE_URL` (prod)
- httpx, django-environ, WhiteNoise, Gunicorn
- Leaflet + MapLibre GL (OpenFreeMap Liberty basemap), Chart.js, Plus Jakarta Sans + Manrope

## 4. Local setup

```bash
cd vajranet
python -m venv .venv
# Windows
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_platform
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/

## 5. Environment variables

See `.env.example`. Important:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django secret |
| `DEBUG` | `False` in production |
| `DATABASE_URL` | Postgres on Render; empty → SQLite |
| `REDIS_URL` | Optional cache backend |
| `MAP_TILE_STYLE_URL` | OpenFreeMap style URL (default Liberty) |
| `MAP_TILE_ATTRIBUTION` | Map attribution HTML/text |
| `AI_PROVIDER` | `platform` (default), `openai`, or `ollama` |
| `OPENAI_API_KEY` | Optional LLM |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Optional local LLM |
| `NASA_FIRMS_MAP_KEY` | Optional wildfire hotspots |
| `IMD_API_KEY` | Reserved for official IMD access |
| `BLITZORTUNG_*` | Reserved; raw lightning redistribution restricted |

## 6. Database

```bash
python manage.py migrate
python manage.py seed_platform
```

Models are PostgreSQL-compatible (indexes, constraints, no SQLite-only features required for prod).

## 7. API integrations (verified)

| Source | Status | Auth | Use |
| --- | --- | --- | --- |
| Open-Meteo Forecast | **Available** | None | Development / evaluation weather |
| Open-Meteo Geocoding | **Available** | None | India-focused city search |
| OpenFreeMap | **Available** | None | Vector basemap (Liberty style) |
| RainViewer | **Available** | None (personal/edu) | Radar tiles (not IMD) |
| USGS Earthquakes | **Available** | None | Observed India bbox events |
| IMD API (`api.imd.gov.in`) | Requires key | 401 without auth | Adapter stub |
| NASA FIRMS | Requires free MAP_KEY | Email signup | Wildfire adapter |
| Lightning | Unavailable | — | No free redistributable feed configured |
| NDMA SACHET | Planned | Agency onboarding | Official CAP alerts |

**Do not invent endpoints.** Provider status is shown on `/data-sources/`.

### Licence distinction

**Free API ≠ unlimited production API ≠ government operational service.**

- **Open-Meteo** free tier: development/non-commercial usage subject to current terms (≈10k calls/day). Not an operational MoES feed.
- **OpenFreeMap**: public map styles; attribution required; no API key.
- **RainViewer**: free API subject to its current personal/educational terms; not official IMD radar.
- **USGS**: public observed earthquake catalog.

For operational/commercial MoES-style deployment, use authorized IMD access and production-grade weather/map infrastructure.

Do **not** use `tile.openstreetmap.org` volunteer raster servers as an application tile endpoint (usage policy / 403 risk).

### Open-Meteo licence note

Free tier is **non-commercial** (≈10k calls/day). For operational/commercial MoES-style deployment, use Open-Meteo paid/customer API or self-host, and integrate IMD with proper authorization.

## 8. Data kind labels

| Label | Meaning |
| --- | --- |
| FORECAST / model analysis | Open-Meteo current & forecast fields |
| MODEL ESTIMATE | Baseline nowcast / derived alerts |
| OBSERVED | USGS quakes, RainViewer radar frames |
| CACHED | Last successful response while live API fails |
| UNAVAILABLE | No legitimate provider configured |

## 9. Key URLs

| Path | Description |
| --- | --- |
| `/` | Dashboard |
| `/nowcasting/` | Thunderstorm risk |
| `/lightning/` | Lightning (or unavailable) |
| `/rainfall/` `/temperature/` `/alerts/` | Monitoring pages |
| `/safety/` | Preparedness |
| `/monitoring/` | Technical view |
| `/data-sources/` | Attribution & status |
| `/health/` | `{ "status": "ok" }` |
| `/admin/` | Django admin |
| `/api/weather/current/?city=Pune` | Current weather API |

## 10. Tests

```bash
pytest
```

External HTTP is mocked. Tests cover models/services/API failure paths, nowcasting, and seed data.

## 11. Lint / format

```bash
ruff check .
black --check .
isort --check-only .
```

## 12. Docker

```bash
docker build -t vajranet .
docker run -p 8000:8000 -e SECRET_KEY=change-me -e DEBUG=False -e ALLOWED_HOSTS=* vajranet
```

## 13. Render deployment

1. Push repo to GitHub
2. Use `render.yaml` or create a Web Service + Postgres
3. Set `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` to your Render hostname
4. `DEBUG=False`
5. Deploy — migrate + seed run on start

## 14. Limitations

- Lightning strikes are **not fabricated**
- Derived alerts are **not official warnings**
- IMD official nowcasts/warnings require API credentials / MoU
- SACHET CAP feed needs agency integration (public page is HTML)
- Map overview hits Open-Meteo per featured city (mitigated by cache)

## 15. Future AI/ML architecture

`NowcastingEngine.predict()` is intentionally replaceable. Future inputs:

Radar + satellite + lightning + observations + NWP → validated 0–60 min thunderstorm/lightning/rainfall probabilities (XGBoost / ConvLSTM / transformers) once labelled datasets and verification exist.

## Disclaimer

Information is for situational awareness and must not replace instructions from IMD, NDMA, or competent authorities.
