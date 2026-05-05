from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def healthcheck() -> dict:
    """Service health check — no authentication required."""
    return {
        "status": "ok",
        "service": "plp-assessment-api",
        "version": "1.0.0",
    }
