from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Category

router = APIRouter(prefix="/categories", tags=["public:categories"])


@router.get("")
async def list_categories(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(select(Category).order_by(Category.name))).scalars().all()
    return [{"id": row.id, "name": row.name, "slug": row.slug} for row in rows]
