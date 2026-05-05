from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, status

from app.config import settings


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
