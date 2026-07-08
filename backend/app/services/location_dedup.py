from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.dedup_keys import normalize_store_name
from app.models import Location

DEFAULT_DEDUP_RADIUS_METERS = 50


def geography_point(wgs_longitude: float, wgs_latitude: float):
    return func.Geography(func.ST_SetSRID(func.ST_MakePoint(wgs_longitude, wgs_latitude), 4326))


async def resolve_canonical_external_id(
    session: AsyncSession,
    *,
    chain_id: int,
    external_id: str,
    name: str | None,
    wgs_latitude: float | None,
    wgs_longitude: float | None,
    run_cache: dict[tuple[int, str, int, int], str],
) -> str:
    normalized_name = normalize_store_name(name)
    if not normalized_name or wgs_latitude is None or wgs_longitude is None:
        return external_id

    cache_key = (
        chain_id,
        normalized_name,
        round(wgs_latitude, 4),
        round(wgs_longitude, 4),
    )
    cached = run_cache.get(cache_key)
    if cached is not None:
        return cached

    point = geography_point(wgs_longitude, wgs_latitude)
    rows = (
        await session.scalars(
            select(Location)
            .where(
                Location.chain_id == chain_id,
                Location.geom.is_not(None),
                func.ST_DWithin(Location.geom, point, DEFAULT_DEDUP_RADIUS_METERS),
            )
            .limit(20)
        )
    ).all()
    for row in rows:
        if normalize_store_name(row.name) == normalized_name:
            run_cache[cache_key] = row.external_id
            return row.external_id

    run_cache[cache_key] = external_id
    return external_id
