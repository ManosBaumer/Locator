# Locater

Geospatial retail-chain location aggregator for China. Map UI (Next.js + MapLibre) backed by a FastAPI API and PostGIS database.

## Architecture

| Component | Local (Docker) | Production |
|-----------|----------------|------------|
| Frontend | `frontend` container (port 3001) | **Netlify** (GitHub deploys) |
| Backend API | `backend` container (port 8000) | Docker host (Render, Railway, Fly, VPS) |
| Database | PostGIS container | **Supabase Postgres** (PostGIS) |

The Next.js app proxies `/api/v1/*` to the FastAPI backend via `BACKEND_URL`.

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
- **Backend**: deploy `backend/Dockerfile` on [Render](https://render.com) via `render.yaml` blueprint
- **Database**: Supabase project `locater` (`ycfvmdehdotogbyrpvdm`, eu-west-1)

### Backend on Render

1. [Render → New → Blueprint](https://dashboard.render.com/blueprints) → connect `ManosBaumer/Locator`
2. Set env vars when prompted:
   - `DATABASE_URL` = `postgresql+asyncpg://postgres.ycfvmdehdotogbyrpvdm:[PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:5432/postgres`
   - `SYNC_DATABASE_URL` = `postgresql+psycopg://postgres.ycfvmdehdotogbyrpvdm:[PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:5432/postgres`
   - `AMAP_API_KEY` = your Amap key
3. After deploy, copy the Render URL (e.g. `https://locater-api.onrender.com`)
4. Set on Netlify: `BACKEND_URL=https://locater-api.onrender.com` and redeploy

### Import McDonald's locations into Supabase

Add `SUPABASE_DB_PASSWORD` to `.env`, then:

```powershell
.\scripts\import-mcdonalds-checkpoint.ps1
```

This imports ~5,800 stores from `data/mcdonalds-checkpoint/` into Supabase.
