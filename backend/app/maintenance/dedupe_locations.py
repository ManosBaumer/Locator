"""Remove duplicate locations that share a chain, name, and nearby coordinates."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.db.session import async_session
from app.ingestion.dedup_keys import normalize_store_name
from app.models import Chain, Location
from app.services.location_dedup import DEFAULT_DEDUP_RADIUS_METERS, geography_point


def _location_score(location: Location) -> tuple[int, int, int]:
    return (
        len(location.address or ""),
        len(location.district or ""),
        len(location.city or ""),
    )


async def dedupe_chain(session, chain: Chain) -> int:
    locations = (
        await session.scalars(
            select(Location)
            .where(Location.chain_id == chain.id, Location.geom.is_not(None))
            .order_by(Location.id)
        )
    ).all()
    deleted = 0
    removed_ids: set[int] = set()

    for location in locations:
        if location.id in removed_ids:
            continue
        normalized_name = normalize_store_name(location.name)
        if not normalized_name or location.longitude is None or location.latitude is None:
            continue

        point = geography_point(float(location.longitude), float(location.latitude))
        neighbors = (
            await session.scalars(
                select(Location).where(
                    Location.chain_id == chain.id,
                    Location.id != location.id,
                    Location.geom.is_not(None),
                    func.ST_DWithin(Location.geom, point, DEFAULT_DEDUP_RADIUS_METERS),
                )
            )
        ).all()

        cluster = [location]
        for neighbor in neighbors:
            if neighbor.id in removed_ids:
                continue
            if normalize_store_name(neighbor.name) == normalized_name:
                cluster.append(neighbor)

        if len(cluster) < 2:
            continue

        keeper = max(cluster, key=_location_score)
        for duplicate in cluster:
            if duplicate.id == keeper.id:
                continue
            await session.delete(duplicate)
            removed_ids.add(duplicate.id)
            deleted += 1

    return deleted


async def main() -> None:
    total_deleted = 0
    async with async_session() as session:
        chains = (await session.scalars(select(Chain))).all()
        for chain in chains:
            deleted = await dedupe_chain(session, chain)
            total_deleted += deleted
            if deleted:
                print(f"{chain.slug}: removed {deleted} duplicates")
        await session.commit()
    print(f"total_removed={total_deleted}")


if __name__ == "__main__":
    asyncio.run(main())
