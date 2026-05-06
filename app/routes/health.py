from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.dependencies import get_job_manager
from app.schemas import HealthResponse
from app.services.job_manager import JobManager

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def healthcheck(
    job_manager: JobManager = Depends(get_job_manager),
) -> HealthResponse:
    """Readiness check for the API and its critical dependencies."""
    redis_ok = await job_manager.ping()
    if not redis_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis dependency is unavailable.",
        )

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.api_version,
        environment=settings.environment,
        dependencies={"redis": "ok"},
        docs={
            "swagger": settings.docs_url,
            "redoc": settings.redoc_url,
            "openapi": settings.openapi_url,
        },
    )
