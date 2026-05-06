from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, Request, status

from app.config import settings
from app.dependencies import get_job_manager, get_pipeline, verify_api_key
from app.rate_limiter import limiter
from app.schemas import EvaluateRequest, EvaluateResponse
from app.services.job_manager import JobManager
from app.services.pipeline import Pipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evaluation"], dependencies=[Depends(verify_api_key)])


def _cleanup_background_task(task: asyncio.Task[None], background_tasks: set) -> None:
    background_tasks.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        logger.warning("Background task %s was cancelled.", task.get_name())
    except Exception:
        logger.exception("Background task %s failed.", task.get_name())


@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(settings.rate_limit_evaluate)
async def submit_evaluation(
    request: Request,
    payload: EvaluateRequest,
    job_manager: JobManager = Depends(get_job_manager),
    pipeline: Pipeline = Depends(get_pipeline),
) -> EvaluateResponse:
    """Submit a full session for AI evaluation."""
    job_id = str(uuid.uuid4())
    await job_manager.create_job(
        job_id=job_id,
        session_id=payload.session_id,
        question_count=len(payload.questions),
    )

    background_task = asyncio.create_task(
        pipeline.process_session(job_id, payload),
        name=f"pipeline:{job_id}",
    )
    request.app.state.background_tasks.add(background_task)
    background_task.add_done_callback(
        lambda task: _cleanup_background_task(task, request.app.state.background_tasks)
    )

    return EvaluateResponse(
        job_id=job_id,
        status="received",
        message=(
            f"Job received. {len(payload.questions)} questions queued for evaluation."
        ),
        poll_url=f"{settings.api_prefix}/status/{job_id}",
    )
