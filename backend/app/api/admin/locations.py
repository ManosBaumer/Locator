from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.auth import require_admin_api_key
from app.db.session import get_session
from app.models import Location

router = APIRouter(
    prefix="/locations",
    tags=["admin:locations"],
    dependencies=[Depends(require_admin_api_key)],
)


@router.get("/{location_id}/raw")
async def get_raw_payload(
    location_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    location = await session.scalar(select(Location).where(Location.id == location_id))
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return {
        "id": location.id,
        "external_id": location.external_id,
        "source_type": location.source_type,
        "source_url": location.source_url,
        "raw_payload": location.raw_payload,
    }
