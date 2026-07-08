from fastapi import APIRouter

from app.api.public.categories import router as categories_router
from app.api.public.chains import router as chains_router
from app.api.public.locations import router as locations_router

router = APIRouter(prefix="/api/v1")
router.include_router(categories_router)
router.include_router(chains_router)
router.include_router(locations_router)
