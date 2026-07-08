# Locater

Geospatial retail-chain location aggregator for China. Map UI (Next.js + MapLibre) backed by a FastAPI API and PostGIS database.

## Architecture

| Component | Local (Docker) | Production |
|-----------|----------------|------------|
| Frontend | `frontend` container (port 3001) | **Netlify** (static GeoJSON + Next.js) |
| Map data | `frontend/public/data/` | Same files, deployed with frontend |
| Ingestion | `backend` container + scrapers | Run locally when updating data |
| Database | PostGIS container (optional Supabase archive) | Not required for the public map |

The map loads **static GeoJSON** from `/data/` — no live API in production. Re-export after ingestion with `python scripts/export-static-data.py`.

## Local development

```bash
cp .env.example .env
docker compose up --build
```

- Map: http://localhost:3001
- API: http://localhost:8000
- Health: http://localhost:8000/health

## Environment variables

See `.env.example`. Key production values:

- `DATABASE_URL` / `SYNC_DATABASE_URL` — Supabase Postgres (async + sync for Alembic)
- `BACKEND_URL` — set on Netlify to your deployed API URL
- `CORS_ORIGINS` — include your Netlify site URL on the backend
- `AMAP_API_KEY` — Amap geocoding for ingestion
- `ADMIN_API_KEY` — protects admin ingestion endpoints

## Database (Supabase)

```bash
cd backend
pip install .
alembic upgrade head
python -m app.db.seed
```

Enable the **postgis** extension in Supabase if not already applied via migration.

## Ingestion

```bash
docker exec -d locater-backend-1 sh -c "python -u -m app.ingestion.runner --chain mcdonalds_deliveryinfo >> /tmp/mcdonalds-deliveryinfo.log 2>&1"
```

See `.cursor/rules/mcdonalds-crawl.mdc` for crawl safety rules.

## Deployment

- **Frontend**: push to `main` → Netlify builds from `netlify.toml` (`base = frontend`)
- **Map data**: static GeoJSON in `frontend/public/data/` (no live backend required)
- **Database**: Supabase for storage; re-export after ingestion updates

### Update map data after ingestion

```powershell
# Requires docker compose db on localhost:5432
python scripts/export-static-data.py
git add frontend/public/data/
git commit -m "Update static map data"
git push
```

Netlify redeploys automatically from GitHub.

### Migrate local Postgres → Supabase (optional archive)

```powershell
python scripts/migrate-local-db-to-supabase.py
```

### Local backend (ingestion only)

```bash
docker compose up
docker compose exec backend python -m app.ingestion.runner --chain mcdonalds_deliveryinfo --from-checkpoint
```

The FastAPI backend is for ingestion and local dev — production map reads static files.
