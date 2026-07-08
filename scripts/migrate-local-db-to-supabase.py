"""Copy all locations from local Docker Postgres into Supabase.

Reads from localhost:5432 (docker compose db) and upserts into Supabase by chain slug.
No scraping — pure database migration.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_URL = os.getenv(
    "LOCAL_DATABASE_URL",
    "postgresql://locater:locater@localhost:5432/locater",
)
PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "ycfvmdehdotogbyrpvdm")
BATCH_SIZE = 500


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
        "Set SUPABASE_DB_PASSWORD in .env before running this script."
    )


def remote_url() -> str:
    from urllib.parse import quote

    password = quote(load_env_password(), safe="")
    return (
        f"postgresql://postgres.{PROJECT_REF}:{password}"
        f"@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
    )


def fetch_local_locations(conn: psycopg.Connection) -> list[dict]:
    query = """
        SELECT
            c.slug AS chain_slug,
            l.external_id,
            l.name,
            l.address,
            l.province,
            l.city,
            l.district,
            l.postal_code,
            l.latitude,
            l.longitude,
            l.coordinate_system::text AS coordinate_system,
            CASE
                WHEN l.geom IS NULL THEN NULL
                ELSE ST_AsText(l.geom::geometry)
            END AS geom_wkt,
            l.source_type,
            l.source_url,
            l.raw_payload,
            l.last_seen_at,
            l.created_at,
            l.updated_at
        FROM locations l
        JOIN chains c ON c.id = l.chain_id
        ORDER BY l.id
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query)
        return list(cur.fetchall())


def main() -> int:
    print(f"Connecting to local DB: {LOCAL_URL.split('@')[-1]}")
    print(f"Connecting to Supabase project: {PROJECT_REF}")

    with psycopg.connect(LOCAL_URL) as local_conn, psycopg.connect(remote_url()) as remote_conn:
        rows = fetch_local_locations(local_conn)
        print(f"Local locations to migrate: {len(rows)}")

        with remote_conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, slug FROM chains")
            chain_ids = {row["slug"]: row["id"] for row in cur.fetchall()}

            cur.execute("TRUNCATE TABLE locations RESTART IDENTITY CASCADE")
            remote_conn.commit()
            print("Cleared existing Supabase locations.")

            insert_sql = """
                INSERT INTO locations (
                    chain_id, external_id, name, address, province, city, district,
                    postal_code, latitude, longitude, coordinate_system, geom,
                    source_type, source_url, raw_payload, last_seen_at, created_at, updated_at
                ) VALUES (
                    %(chain_id)s, %(external_id)s, %(name)s, %(address)s, %(province)s,
                    %(city)s, %(district)s, %(postal_code)s, %(latitude)s, %(longitude)s,
                    %(coordinate_system)s,
                    CASE
                        WHEN %(has_geom)s THEN ST_GeogFromText(%(geom_wkt)s)::extensions.geography
                        ELSE NULL
                    END,
                    %(source_type)s, %(source_url)s, %(raw_payload)s,
                    %(last_seen_at)s, %(created_at)s, %(updated_at)s
                )
            """

            migrated = 0
            for start in range(0, len(rows), BATCH_SIZE):
                batch = rows[start : start + BATCH_SIZE]
                payload = []
                for row in batch:
                    chain_id = chain_ids.get(row["chain_slug"])
                    if chain_id is None:
                        print(f"Skipping unknown chain slug: {row['chain_slug']}", file=sys.stderr)
                        continue
                    item = dict(row)
                    item["chain_id"] = chain_id
                    item["raw_payload"] = Json(item["raw_payload"] or {})
                    item["has_geom"] = item["geom_wkt"] is not None
                    payload.append(item)
                with remote_conn.cursor() as writer:
                    writer.executemany(insert_sql, payload)
                remote_conn.commit()
                migrated += len(payload)
                print(f"Migrated {migrated}/{len(rows)}")

            cur.execute(
                """
                SELECT c.slug, count(l.id)::int AS count
                FROM chains c
                LEFT JOIN locations l ON l.chain_id = c.id
                GROUP BY c.slug
                ORDER BY count DESC
                """
            )
            print("\nSupabase counts after migration:")
            for row in cur.fetchall():
                print(f"  {row['slug']}: {row['count']}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
