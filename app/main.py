from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.error_handlers import register_error_handlers
from app.logging_config import setup_logging
from app.middleware import TimeoutMiddleware
from app.rate_limiter import limiter
from app.routes import evaluate, health, status
from app.services.job_manager import JobManager
from app.services.pipeline import Pipeline


setup_logging(settings.log_level, settings.environment)
logger = logging.getLogger(__name__)


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": f"Too many requests. Limit: {exc.detail}",
            "status_code": 429,
        },
    )


async def _shutdown_background_tasks(tasks: set[asyncio.Task[Any]]) -> None:
    if not tasks:
        return

    logger.info("Waiting for %d background task(s) to finish.", len(tasks))
    done, pending = await asyncio.wait(tasks, timeout=10)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        try:
            task.result()
        except asyncio.CancelledError:
            logger.warning("Background task %s was cancelled during shutdown.", task)
        except Exception:
            logger.exception("Background task failed during shutdown.")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings.validate_runtime()
    settings.effective_temp_dir

    job_manager = getattr(app.state, "job_manager", None) or JobManager()
    pipeline = getattr(app.state, "pipeline", None) or Pipeline(job_manager=job_manager)
    background_tasks = getattr(app.state, "background_tasks", None)
    if background_tasks is None:
        background_tasks = set()

    app.state.job_manager = job_manager
    app.state.pipeline = pipeline
    app.state.background_tasks = background_tasks

    logger.info(
        "%s starting: env=%s model=%s whisper=%s redis=%s docs=%s redoc=%s",
        settings.app_name,
        settings.environment,
        settings.openai_model,
        "faster-whisper" if settings.use_faster_whisper else "openai-only",
        settings.masked_redis_url,
        settings.docs_url,
        settings.redoc_url,
    )
    try:
        yield
    finally:
        await _shutdown_background_tasks(app.state.background_tasks)

        pipeline_close = getattr(app.state.pipeline, "close", None)
        if pipeline_close is not None:
            await pipeline_close()

        job_manager_close = getattr(app.state.job_manager, "close", None)
        if job_manager_close is not None:
            await job_manager_close()
        logger.info("%s shutting down.", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=settings.api_description,
        version=settings.api_version,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        openapi_url=settings.openapi_url,
        lifespan=_lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    register_error_handlers(app)

    app.add_middleware(
        TimeoutMiddleware,
        timeout_seconds=settings.request_timeout_seconds,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(evaluate.router, prefix=settings.api_prefix)
    app.include_router(status.router, prefix=settings.api_prefix)

    return app


app = create_app()
