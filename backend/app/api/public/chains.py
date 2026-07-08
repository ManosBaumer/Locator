from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ingestion.amap_regions import apply_mainland_scope_filter
from app.db.session import get_session
from app.models import Category, Chain, Location

router = APIRouter(prefix="/chains", tags=["public:chains"])


@router.get("")
async def list_chains(
    category: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    stmt = select(Chain).options(selectinload(Chain.category)).join(Chain.category)
    if category:
        stmt = stmt.where(Category.slug == category)
    rows = (await session.execute(stmt.order_by(Chain.name))).scalars().all()

    count_rows = await session.execute(
        apply_mainland_scope_filter(
            select(Chain.slug, func.count(Location.id))
            .join(Location, Location.chain_id == Chain.id, isouter=True)
            .group_by(Chain.slug),
            Location,
        )
    )
    location_counts = dict(count_rows.all())

    return [
        {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "category_slug": row.category.slug,
            "country": row.country,
            "website": row.website,
            "store_locator_url": row.store_locator_url,
            "location_count": location_counts.get(row.slug, 0),
        }
        for row in rows
    ]


@router.get("/{slug}/locations")
async def list_chain_locations(
    slug: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    stmt = apply_mainland_scope_filter(
        select(Location, Chain)
        .join(Chain, Chain.id == Location.chain_id)
        .where(Chain.slug == slug)
        .order_by(Location.name)
        .limit(limit)
        .offset(offset),
        Location,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": location.id,
            "external_id": location.external_id,
            "name": location.name,
            "address": location.address,
            "city": location.city,
            "chain_slug": chain.slug,
            "latitude": float(location.latitude) if location.latitude is not None else None,
            "longitude": float(location.longitude) if location.longitude is not None else None,
            "coordinate_system": location.coordinate_system.value,
        }
        for location, chain in rows
    ]
