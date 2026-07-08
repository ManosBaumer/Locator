import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.admin.auth import require_admin_api_key
from app.db.session import async_session
from app.ingestion.adapters import aldi, family_mart, hema, kfc, rt_mart, seven_eleven, seven_fresh  # noqa: F401
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.registry import get_adapter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["admin:sync"], dependencies=[Depends(require_admin_api_key)])


@router.post("/{chain_slug}")
async def trigger_sync(chain_slug: str, background_tasks: BackgroundTasks) -> dict:
    background_tasks.add_task(_run_sync, chain_slug)
    return {"status": "queued", "chain_slug": chain_slug}


async def _run_sync(chain_slug: str) -> None:
    async with async_session() as session:
        adapter = get_adapter(chain_slug)
        await IngestionPipeline(session, adapter).run()
