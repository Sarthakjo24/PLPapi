from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import Header, HTTPException, Request, status

from app.config import settings

if TYPE_CHECKING:
    from app.services.job_manager import JobManager
    from app.services.pipeline import Pipeline


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """Validate the X-API-Key header against the configured key."""
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key.",
        )
    return x_api_key


def get_job_manager(request: Request) -> "JobManager":
    return request.app.state.job_manager


def get_pipeline(request: Request) -> "Pipeline":
    return request.app.state.pipeline
