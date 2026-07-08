from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Location
from app.models.enums import CoordinateSystem


async def upsert_location(
    session: AsyncSession,
    *,
    chain_id: int,
    external_id: str,
    name: str | None,
    address: str | None,
    province: str | None,
    city: str | None,
    district: str | None,
    postal_code: str | None,
    latitude: float | None,
    longitude: float | None,
    coordinate_system: CoordinateSystem,
    wgs84_latitude: float | None,
    wgs84_longitude: float | None,
    source_type: str,
    source_url: str | None,
    raw_payload: dict,
    seen_at: datetime,
) -> None:
    geom = (
        f"SRID=4326;POINT({wgs84_longitude} {wgs84_latitude})"
        if wgs84_latitude is not None and wgs84_longitude is not None
        else None
    )
    stmt = insert(Location).values(
        chain_id=chain_id,
        external_id=external_id,
        name=name,
        address=address,
        province=province,
        city=city,
        district=district,
        postal_code=postal_code,
        latitude=latitude,
        longitude=longitude,
        coordinate_system=coordinate_system,
        geom=geom,
        source_type=source_type,
        source_url=source_url,
        raw_payload=raw_payload,
        last_seen_at=seen_at,
        updated_at=seen_at,
    )
    updates = {
        "name": stmt.excluded.name,
        "address": stmt.excluded.address,
        "province": stmt.excluded.province,
        "city": stmt.excluded.city,
        "district": stmt.excluded.district,
        "postal_code": stmt.excluded.postal_code,
        "latitude": stmt.excluded.latitude,
        "longitude": stmt.excluded.longitude,
        "coordinate_system": stmt.excluded.coordinate_system,
        "geom": stmt.excluded.geom,
        "source_type": stmt.excluded.source_type,
        "source_url": stmt.excluded.source_url,
        "raw_payload": stmt.excluded.raw_payload,
        "last_seen_at": stmt.excluded.last_seen_at,
        "updated_at": stmt.excluded.updated_at,
    }
    await session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_locations_chain_external",
            set_=updates,
        )
    )
