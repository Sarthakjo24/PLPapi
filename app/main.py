from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.error_handlers import register_error_handlers
from app.logging_config import setup_logging
from app.middleware import TimeoutMiddleware
from app.routes import evaluate, health, status


# ── Initialize structured logging ──
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

# ── Rate limiter ──
limiter = Limiter(key_func=get_remote_address)


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": f"Too many requests. Limit: {exc.detail}",
            "status_code": 429,
        },
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # ── startup ──
    settings.effective_temp_dir  # ensure temp dir exists
    logger.info(
        "PLP Assessment API starting — env=%s model=%s whisper=%s redis=%s",
        settings.environment,
        settings.openai_model,
        "faster-whisper" if settings.use_faster_whisper else "openai-only",
        settings.redis_url.split("@")[-1] if "@" in settings.redis_url else settings.redis_url,
    )
    yield
    # ── shutdown ──
    logger.info("PLP Assessment API shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="PLP Assessment API",
        description="AI-powered candidate assessment service for WMS integration.",
        version="1.0.0",
        docs_url=None,  # Temporarily disabled due to OpenAPI schema generation issue
        redoc_url=None,  # Temporarily disabled due to OpenAPI schema generation issue
        lifespan=_lifespan,
    )

    # ── Rate limiter ──
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    # ── Standardized error responses ──
    register_error_handlers(app)

    # ── Request timeout middleware ──
    app.add_middleware(TimeoutMiddleware, timeout_seconds=settings.request_timeout_seconds)

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ──
    app.include_router(health.router, prefix="/api/v1")      # no auth
    app.include_router(evaluate.router, prefix="/api/v1")     # API key required
    app.include_router(status.router, prefix="/api/v1")       # API key required

    return app


app = create_app()
