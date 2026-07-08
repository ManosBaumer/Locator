import argparse
import asyncio
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import async_session
from app.ingestion.adapters.mcdonalds_deliveryinfo import McDonaldsDeliveryinfoAdapter
from app.ingestion.registry import get_adapter
from app.ingestion.single_instance import SingleInstanceLock
from app.models import Chain, Location
from app.models.enums import CoordinateSystem

# Import adapter modules so decorators populate the registry.
from app.ingestion.adapters import (  # noqa: F401
    aldi,
    costco,
    family_mart,
    hema,
    kfc,
    mcdonalds,
    mcdonalds_deliveryinfo,
    rt_mart,
    seven_eleven,
    seven_fresh,
    walmart,
    yonghui,
)
from app.ingestion.pipeline import IngestionPipeline


async def load_mcdonalds_stores_from_db(session) -> dict[str, dict]:
    chain = await session.scalar(select(Chain).where(Chain.slug == "mcdonalds"))
    if chain is None:
        return {}
    rows = (
        await session.scalars(select(Location).where(Location.chain_id == chain.id))
    ).all()
    stores: dict[str, dict] = {}
    for row in rows:
        coord = row.coordinate_system
        if isinstance(coord, CoordinateSystem):
            coord_value = coord.value
        else:
            coord_value = str(coord)
        stores[row.external_id] = {
            "external_id": row.external_id,
            "name": row.name,
            "address": row.address,
            "province": row.province,
            "city": row.city,
            "district": row.district,
            "latitude": float(row.latitude) if row.latitude is not None else None,
            "longitude": float(row.longitude) if row.longitude is not None else None,
            "coordinate_system": coord_value,
            "raw": row.raw_payload or {},
        }
    return stores


async def run_chain(
    chain_slug: str,
    *,
    from_checkpoint: bool = False,
    gap_fill_only: bool = False,
    cities: set[str] | None = None,
    cities_min_disclosure: int | None = None,
) -> int:
    async with async_session() as session:
        adapter = get_adapter(chain_slug)
        if isinstance(adapter, McDonaldsDeliveryinfoAdapter):
            adapter.cities_filter = cities
            adapter.cities_min_disclosure = cities_min_disclosure
            adapter.gap_fill_only = gap_fill_only
            if gap_fill_only:
                adapter.existing_stores = await load_mcdonalds_stores_from_db(session)

        pipeline = IngestionPipeline(session, adapter)
        if from_checkpoint:
            if chain_slug not in ("mcdonalds", "mcdonalds_deliveryinfo"):
                raise ValueError(
                    "--from-checkpoint is only supported for mcdonalds and mcdonalds_deliveryinfo"
                )
            if not hasattr(adapter, "load_checkpoint_stores"):
                raise ValueError(f"Adapter {chain_slug} does not support --from-checkpoint")
            raw_data = adapter.load_checkpoint_stores()
            run = await pipeline.upsert_raw_data(raw_data)
        else:
            run = await pipeline.run()
        return run.id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a chain ingestion adapter.")
    parser.add_argument("--chain", required=True, help="Chain slug, for example: hema")
    parser.add_argument(
        "--from-checkpoint",
        action="store_true",
        help="Upsert stores from a McDonald's checkpoint without running a new crawl",
    )
    parser.add_argument(
        "--gap-fill-only",
        action="store_true",
        help="Fill unmatched disclosure stores via Amap POI + McDonald's API (deliveryinfo only)",
    )
    parser.add_argument(
        "--cities",
        help="Comma-separated city names to crawl or re-crawl (deliveryinfo only)",
    )
    parser.add_argument(
        "--cities-min-disclosure",
        type=int,
        help=(
            "Re-crawl every city whose disclosure store count is >= N "
            "(deliveryinfo only). Avoids passing many city names on the CLI."
        ),
    )
    args = parser.parse_args()

    cities: set[str] | None = None
    if args.cities:
        cities = {part.strip() for part in args.cities.split(",") if part.strip()}

    configure_logging(get_settings().log_level)
    lock: SingleInstanceLock | None = None
    if args.chain in ("mcdonalds", "mcdonalds_deliveryinfo") and not args.from_checkpoint:
        lock = SingleInstanceLock(Path(f"/tmp/{args.chain}-ingest.lock"))
        lock.acquire()
    try:
        run_id = asyncio.run(
            run_chain(
                args.chain,
                from_checkpoint=args.from_checkpoint,
                gap_fill_only=args.gap_fill_only,
                cities=cities,
                cities_min_disclosure=args.cities_min_disclosure,
            )
        )
    finally:
        if lock is not None:
            lock.release()
    print(f"ingestion_run_id={run_id}")


if __name__ == "__main__":
    main()
