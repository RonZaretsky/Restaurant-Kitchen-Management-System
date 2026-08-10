from fastapi import APIRouter
from pydantic import BaseModel

from api.admin import router as admin_router
from api.auth import router as auth_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(admin_router)


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
