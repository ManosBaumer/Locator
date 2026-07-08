from fastapi import APIRouter

from app.api.admin.locations import router as locations_router
from app.api.admin.runs import router as runs_router
from app.api.admin.sync import router as sync_router

router = APIRouter(prefix="/api/v1/admin")
router.include_router(sync_router)
router.include_router(runs_router)
router.include_router(locations_router)
