"""Request timeout middleware.

Wraps each incoming request in asyncio.wait_for with a configurable timeout.
Returns 504 Gateway Timeout if the request handler exceeds the limit.

This prevents hung OpenAI/transcription calls from holding connections forever.
"""
from __future__ import annotations

import asyncio
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces a per-request timeout."""

    def __init__(self, app, timeout_seconds: int = 180) -> None:
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Request timed out after %ds: %s %s",
                self.timeout_seconds,
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=504,
                content={
                    "error": "Gateway Timeout",
                    "detail": (
                        f"Request exceeded the {self.timeout_seconds}s timeout. "
                        "The server is still processing your job in the background."
                    ),
                    "status_code": 504,
                },
            )
