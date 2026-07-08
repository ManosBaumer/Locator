"""Export categories, chains, and per-chain GeoJSON for static Netlify hosting.

Reads from local Docker Postgres by default. Re-run after ingestion, then commit
frontend/public/data/ and push to deploy updated map data.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "frontend" / "public" / "data"
LOCATIONS_DIR = OUT_DIR / "locations"

LOCAL_URL = os.getenv(
    "LOCAL_DATABASE_URL",
    "postgresql://locater:locater@localhost:5432/locater",
)

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
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOCATIONS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Exporting from {LOCAL_URL.split('@')[-1]}")
    with psycopg.connect(LOCAL_URL) as conn:
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
