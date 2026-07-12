import json
import math

from fastapi import APIRouter, Depends, Query
from geoalchemy2 import Geometry
from sqlalchemy import cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.amap_regions import apply_mainland_scope_filter
from app.db.session import get_session
from app.models import Category, Chain, Location

router = APIRouter(prefix="/locations", tags=["public:locations"])

# Cap bbox payloads for map rendering; when exceeded, thin points on a grid so every
# region is represented instead of returning an arbitrary first N rows.
MAX_BBOX_FEATURES = 50_000


@router.get("/bbox")
async def bbox_locations(
    min_lng: float = Query(...),
    min_lat: float = Query(...),
    max_lng: float = Query(...),
    max_lat: float = Query(...),
    categories: str | None = Query(default=None),
    chains: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    bbox = func.Geography(func.ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326))
    total = await _bbox_count(session, bbox, categories, chains)

    if total <= MAX_BBOX_FEATURES:
        stmt = _bbox_geojson_stmt(bbox, categories, chains)
        rows = (await session.execute(stmt)).all()
    else:
        rows = await _bbox_sampled_rows(
            session, bbox, categories, chains, min_lng, min_lat, max_lng, max_lat
        )

    return _feature_collection(rows)


@router.get("/nearby")
async def nearby_locations(
    lng: float = Query(...),
    lat: float = Query(...),
    radius_m: int = Query(default=3000, ge=1, le=100000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    point = func.Geography(func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326))
    stmt = _base_geojson_stmt().where(func.ST_DWithin(Location.geom, point, radius_m)).limit(500)
    rows = (await session.execute(stmt)).all()
    return _feature_collection(rows)


@router.get("/search")
async def search_locations(
    q: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
) -> dict:
    pattern = f"%{q}%"
    stmt = _base_geojson_stmt().where(
        or_(Location.name.ilike(pattern), Location.address.ilike(pattern), Location.city.ilike(pattern))
    )
    rows = (await session.execute(stmt.limit(100))).all()
    return _feature_collection(rows)


def _base_geojson_stmt():
    stmt = (
        select(
            Location.id,
            Location.name,
            Location.address,
            Location.city,
            Chain.slug.label("chain_slug"),
            Category.slug.label("category_slug"),
            func.ST_AsGeoJSON(Location.geom).label("geometry"),
        )
        .join(Chain, Chain.id == Location.chain_id)
        .join(Category, Category.id == Chain.category_id)
        .where(Location.geom.is_not(None))
    )
    return apply_mainland_scope_filter(stmt, Location)


def _bbox_geojson_stmt(bbox, categories: str | None, chains: str | None):
    stmt = _base_geojson_stmt().where(func.ST_Intersects(Location.geom, bbox))
    return _apply_filters(stmt, categories, chains)


async def _bbox_count(
    session: AsyncSession,
    bbox,
    categories: str | None,
    chains: str | None,
) -> int:
    stmt = apply_mainland_scope_filter(
        select(func.count(Location.id))
        .select_from(Location)
        .join(Chain, Chain.id == Location.chain_id)
        .join(Category, Category.id == Chain.category_id)
        .where(Location.geom.is_not(None))
        .where(func.ST_Intersects(Location.geom, bbox)),
        Location,
    )
    stmt = _apply_filters(stmt, categories, chains)
    return int(await session.scalar(stmt) or 0)


def _bbox_grid_degrees(
    min_lng: float,
    min_lat: float,
    max_lng: float,
    max_lat: float,
    max_features: int,
) -> float:
    width = max(max_lng - min_lng, 0.001)
    height = max(max_lat - min_lat, 0.001)
    return max(math.sqrt(width * height / max_features) * 0.9, 0.002)


async def _bbox_sampled_rows(
    session: AsyncSession,
    bbox,
    categories: str | None,
    chains: str | None,
    min_lng: float,
    min_lat: float,
    max_lng: float,
    max_lat: float,
):
    grid_deg = _bbox_grid_degrees(min_lng, min_lat, max_lng, max_lat, MAX_BBOX_FEATURES)
    geom = cast(Location.geom, Geometry(geometry_type="POINT", srid=4326))
    grid = func.ST_SnapToGrid(geom, grid_deg, grid_deg)

    ranked = apply_mainland_scope_filter(
        select(
            Location.id,
            Location.name,
            Location.address,
            Location.city,
            Chain.slug.label("chain_slug"),
            Category.slug.label("category_slug"),
            func.ST_AsGeoJSON(Location.geom).label("geometry"),
            func.row_number().over(partition_by=grid, order_by=Location.id).label("rn"),
        )
        .join(Chain, Chain.id == Location.chain_id)
        .join(Category, Category.id == Chain.category_id)
        .where(Location.geom.is_not(None))
        .where(func.ST_Intersects(Location.geom, bbox)),
        Location,
    )
    ranked = _apply_filters(ranked, categories, chains).subquery()

    stmt = (
        select(
            ranked.c.id,
            ranked.c.name,
            ranked.c.address,
            ranked.c.city,
            ranked.c.chain_slug,
            ranked.c.category_slug,
            ranked.c.geometry,
        )
        .where(ranked.c.rn == 1)
        .limit(MAX_BBOX_FEATURES)
    )
    return (await session.execute(stmt)).all()


def _apply_filters(stmt, categories: str | None, chains: str | None):
    category_slugs = _csv(categories)
    chain_slugs = _csv(chains)
    if category_slugs:
        stmt = stmt.where(Category.slug.in_(category_slugs))
    if chain_slugs:
        stmt = stmt.where(Chain.slug.in_(chain_slugs))
    return stmt


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _feature_collection(rows) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": row.id,
                "geometry": json.loads(row.geometry),
                "properties": {
                    "id": row.id,
                    "name": row.name,
                    "chain_slug": row.chain_slug,
                    "category_slug": row.category_slug,
                    "address": row.address,
                    "city": row.city,
                },
            }
            for row in rows
            if row.geometry
        ],
    }
