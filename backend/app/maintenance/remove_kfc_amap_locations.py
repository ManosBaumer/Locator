"""Drop legacy KFC rows ingested from Amap POI search; keep store-portal records."""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, func, select

from app.db.session import async_session
from app.models import Chain, Location


async def main() -> None:
    async with async_session() as session:
        kfc = await session.scalar(select(Chain).where(Chain.slug == "kfc"))
        if kfc is None:
            raise SystemExit("Chain not found: kfc")

        count = await session.scalar(
            select(func.count())
            .select_from(Location)
            .where(Location.chain_id == kfc.id, Location.source_type == "amap_poi")
        )
        if not count:
            print("kfc_amap_removed=0")
            return

        await session.execute(
            delete(Location).where(Location.chain_id == kfc.id, Location.source_type == "amap_poi")
        )
        await session.commit()
        print(f"kfc_amap_removed={count}")


if __name__ == "__main__":
    asyncio.run(main())
