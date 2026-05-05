"""Standardized error responses.

Every error returns consistent JSON:
  {"error": "Short title", "detail": "Description", "status_code": 500}
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_IS_PROD = os.getenv("ENV", "dev").strip().lower() == "prod"


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "detail": detail,
            "status_code": status_code,
        },
    )


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return _error_response(
        status_code=exc.status_code,
        error=exc.detail if isinstance(exc.detail, str) else "Request error",
        detail=str(exc.detail),
    )


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    # Build a readable summary of what fields failed
    field_errors = []
    for err in errors:
        loc = " → ".join(str(part) for part in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        field_errors.append(f"{loc}: {msg}")

    return _error_response(
        status_code=422,
        error="Validation error",
        detail="; ".join(field_errors) if field_errors else "Invalid request payload.",
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)

    # Hide internals in production
    detail = "Internal server error. Please try again later."
    if not _IS_PROD:
        detail = f"{type(exc).__name__}: {exc}"

    return _error_response(
        status_code=500,
        error="Internal server error",
        detail=detail,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach all error handlers to the FastAPI app."""
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
