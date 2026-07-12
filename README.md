# Mitu

Geospatial retail-chain location aggregator for China. Map UI (Next.js + MapLibre) served from static GeoJSON — no live API required for viewing.

## Architecture

| Component | Local | Production |
|-----------|-------|------------|
| Frontend | `npm run dev` in `frontend/` | **Netlify** (Next.js + static GeoJSON) |
| Map data | `frontend/public/data/` | Same files, deployed with frontend |
| Database | **Supabase** (archive + export source) | Supabase |
| Ingestion | Docker `db` + `backend` (optional) | Run locally when updating data |

The map loads **static GeoJSON** from `/data/` — same locally and on Netlify.

## Local development (map only)

No Docker or backend needed to view the map:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 — data comes from `frontend/public/data/`.

To refresh map files from Supabase (after ingestion or DB updates):

```powershell
# SUPABASE_DB_PASSWORD must be set in .env
python scripts/export-static-data.py
```

Use `--local` if you still have Docker Postgres on `localhost:5432`:

```powershell
python scripts/export-static-data.py --local
```

## Ingestion (optional — Docker)

Only needed when scraping or importing new location data:

```bash
docker compose --profile ingest up --build
```

- API (ingestion/admin): http://localhost:8000
- McDonald's crawl: see `.cursor/rules/mcdonalds-crawl.mdc`

After ingestion, export static data and push:

```powershell
python scripts/export-static-data.py
git add frontend/public/data/
git commit -m "Update static map data"
git push
```

### Mixue (蜜雪冰城) — static scrape (no Docker)

Uses the WeChat mini-program API (`scripts/lib/mixue-api.js`). **Per-city** bounded adaptive grid (~370 prefecture centers from Amap), writes GeoJSON directly:

```powershell
node scripts/scrape-mixue.js              # all mainland cities (~hours; resumable)
node scripts/scrape-mixue.js --test-guangzhou
node scripts/scrape-mixue.js --resume     # after interrupt (migrates old nationwide checkpoints)
node scripts/scrape-mixue.js --region east-south
```

Requires `AMAP_API_KEY` in `.env` on first run (caches city list to `data/mixue-city-centers.json`).

After the city crawl, add countryside stores without losing city data:

```powershell
node scripts/scrape-mixue.js --backup-city --resume          # snapshot → data/mixue-city-backup.json
node scripts/scrape-mixue.js --merge-grid --resume --workers 16  # nationwide grid, deduped by shop id
```

Output: `frontend/public/data/locations/mixue.geojson` (checkpoint in `data/mixue-checkpoint.json`, gitignored).

Then commit `frontend/public/data/` and logos under `frontend/public/logos/mixue*.png`.

## Environment variables

See `.env.example` for ingestion (Docker + Supabase). For the map frontend, only optional:

- `NEXT_PUBLIC_MAP_TILE_URL` — MapLibre style URL (see `frontend/.env.example`)

Ingestion-related:

- `DATABASE_URL` / `SYNC_DATABASE_URL` — Postgres for scrapers
- `SUPABASE_DB_PASSWORD` / `SUPABASE_PROJECT_REF` — export script → Supabase
- `AMAP_API_KEY` — Amap geocoding for ingestion
- `ADMIN_API_KEY` — protects admin ingestion endpoints

## Database (Supabase)

Schema and seed are applied via Supabase migrations. Enable **postgis** if not already present.

## Deployment

- **Frontend**: push to `main` → Netlify builds from `netlify.toml` (`base = frontend`)
- **Map data**: static GeoJSON in `frontend/public/data/` — commit and push to deploy updates
- No `BACKEND_URL` or live API on Netlify

### Migrate local Postgres → Supabase (one-time)

```powershell
python scripts/migrate-local-db-to-supabase.py
```
