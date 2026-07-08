"""Export categories, chains, and per-chain GeoJSON for static hosting.

Reads from Supabase by default (set SUPABASE_DB_PASSWORD in .env).
Use --local to export from Docker Postgres on localhost:5432 instead.

Re-run after ingestion, then commit frontend/public/data/ and push to deploy.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "frontend" / "public" / "data"
LOCATIONS_DIR = OUT_DIR / "locations"

LOCAL_URL = os.getenv(
    "LOCAL_DATABASE_URL",
    "postgresql://locater:locater@localhost:5432/locater",
)
PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "ycfvmdehdotogbyrpvdm")

EXCLUDED_PREFIXES = ("台湾", "台灣", "香港", "澳门", "澳門")


def load_env_password() -> str:
    password = os.getenv("SUPABASE_DB_PASSWORD", "").strip()
    if password:
        return password
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SUPABASE_DB_PASSWORD="):
                return line.split("=", 1)[1].strip()
    raise SystemExit(
        "Set SUPABASE_DB_PASSWORD in .env (or pass --local with Docker Postgres running)."
    )


def supabase_url() -> str:
    password = quote(load_env_password(), safe="")
    return (
        f"postgresql://postgres.{PROJECT_REF}:{password}"
        f"@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
    )


def resolve_database_url(use_local: bool) -> str:
    if use_local:
        return LOCAL_URL
    return supabase_url()

EXCLUDED_PREFIXES = ("台湾", "台灣", "香港", "澳门", "澳門")


def mainland_filter_sql() -> str:
    clauses = []
    for prefix in EXCLUDED_PREFIXES:
        clauses.append(f"(l.province IS NULL OR l.province NOT LIKE '{prefix}%%')")
        clauses.append(f"(l.city IS NULL OR l.city NOT LIKE '{prefix}%%')")
    return " AND ".join(clauses)


def export_categories(conn: psycopg.Connection) -> None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, name, slug FROM categories ORDER BY name")
        rows = cur.fetchall()
    (OUT_DIR / "categories.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"categories: {len(rows)}")


def export_chains(conn: psycopg.Connection) -> None:
    query = """
        SELECT
            c.id,
            c.name,
            c.slug,
            cat.slug AS category_slug,
            count(l.id)::int AS location_count
        FROM chains c
        JOIN categories cat ON cat.id = c.category_id
        LEFT JOIN locations l ON l.chain_id = c.id AND l.geom IS NOT NULL
        GROUP BY c.id, c.name, c.slug, cat.slug
        ORDER BY c.name
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query)
        rows = cur.fetchall()
    (OUT_DIR / "chains.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"chains: {len(rows)}")


def export_chain_locations(conn: psycopg.Connection, chain_slug: str) -> int:
    query = f"""
        SELECT
            l.id,
            l.name,
            l.address,
            l.city,
            c.slug AS chain_slug,
            cat.slug AS category_slug,
            ST_AsGeoJSON(l.geom::geometry) AS geometry
        FROM locations l
        JOIN chains c ON c.id = l.chain_id
        JOIN categories cat ON cat.id = c.category_id
        WHERE c.slug = %(slug)s
          AND l.geom IS NOT NULL
          AND {mainland_filter_sql()}
        ORDER BY l.id
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, {"slug": chain_slug})
        rows = cur.fetchall()

    features = []
    for row in rows:
        if not row["geometry"]:
            continue
        features.append(
            {
                "type": "Feature",
                "id": row["id"],
                "geometry": json.loads(row["geometry"]),
                "properties": {
                    "id": row["id"],
                    "name": row["name"],
                    "chain_slug": row["chain_slug"],
                    "category_slug": row["category_slug"],
                    "address": row["address"],
                    "city": row["city"],
                },
            }
        )

    payload = {"type": "FeatureCollection", "features": features}
    path = LOCATIONS_DIR / f"{chain_slug}.geojson"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return len(features)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export static map GeoJSON from Postgres.")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Read from local Docker Postgres (localhost:5432) instead of Supabase.",
    )
    args = parser.parse_args()

    database_url = resolve_database_url(args.local)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOCATIONS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Exporting from {database_url.split('@')[-1]}")
    with psycopg.connect(database_url) as conn:
        export_categories(conn)
        export_chains(conn)

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT slug FROM chains ORDER BY slug")
            chain_slugs = [row["slug"] for row in cur.fetchall()]

        total = 0
        for slug in chain_slugs:
            count = export_chain_locations(conn, slug)
            total += count
            print(f"  {slug}: {count}")

    manifest = {"chains": chain_slugs, "location_count": total}
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Done. {total} locations in {LOCATIONS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
