from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.admin.auth import require_admin_api_key
from app.db.session import get_session
from app.models import IngestionFailure, IngestionRun

router = APIRouter(prefix="/runs", tags=["admin:runs"], dependencies=[Depends(require_admin_api_key)])


@router.get("")
async def list_runs(
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (
        await session.execute(
            select(IngestionRun)
            .options(selectinload(IngestionRun.chain))
            .order_by(IngestionRun.started_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [_run_dict(row) for row in rows]


@router.get("/{run_id}")
async def get_run(run_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    run = await session.scalar(
        select(IngestionRun).options(selectinload(IngestionRun.chain)).where(IngestionRun.id == run_id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_dict(run)


@router.get("/{run_id}/failures")
async def list_failures(
    run_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (
        await session.execute(
            select(IngestionFailure)
            .where(IngestionFailure.run_id == run_id)
            .order_by(IngestionFailure.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "run_id": row.run_id,
            "external_id": row.external_id,
            "stage": row.stage,
            "reason": row.reason,
            "raw_payload": row.raw_payload,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def _run_dict(run: IngestionRun) -> dict:
    return {
        "id": run.id,
        "chain_slug": run.chain.slug,
        "status": run.status.value,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "fetched_count": run.fetched_count,
        "parsed_count": run.parsed_count,
        "upserted_count": run.upserted_count,
        "failed_count": run.failed_count,
        "adapter_version": run.adapter_version,
        "source_url": run.source_url,
        "error_summary": run.error_summary,
    }
