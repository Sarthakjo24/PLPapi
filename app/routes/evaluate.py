from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Body, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import verify_api_key
from app.schemas import EvaluateRequest, EvaluateResponse
from app.services.job_manager import JobManager
from app.services.pipeline import Pipeline

router = APIRouter(tags=["evaluation"], dependencies=[Depends(verify_api_key)])
limiter = Limiter(key_func=get_remote_address)

# Shared instances (initialized at import, reused across requests)
_job_manager = JobManager()
_pipeline = Pipeline(job_manager=_job_manager)


@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(settings.rate_limit_evaluate)
async def submit_evaluation(
    request: Request,
    payload: EvaluateRequest = Body(...),
) -> EvaluateResponse:
    """Submit a full session (1-10 questions) for AI evaluation.

    Returns a job_id immediately. Poll /status/{job_id} for results.
    """
    errors: list[str] = []
    for q in payload.questions:
        if not q.recording_url.strip():
            errors.append(f"Missing recording_url for question {q.question_id}.")
        if not q.standard_responses or all(
            not s.strip() for s in q.standard_responses
        ):
            errors.append(
                f"Missing standard_responses for question {q.question_id}."
            )
        if not q.question_text.strip():
            errors.append(f"Missing question_text for question {q.question_id}.")

    if errors:
        return EvaluateResponse(
            job_id=None,
            status="rejected",
            message=(
                "Payload validation failed. Please resend with corrections: "
                + "; ".join(errors)
            ),
        )

    # ── Create job and start background processing ──
    job_id = str(uuid.uuid4())
    await _job_manager.create_job(
        job_id=job_id,
        session_id=payload.session_id,
        question_count=len(payload.questions),
    )

    # Fire-and-forget background task
    asyncio.create_task(_pipeline.process_session(job_id, payload))

    return EvaluateResponse(
        job_id=job_id,
        status="received",
        message=f"Job received. {len(payload.questions)} questions queued for evaluation.",
        poll_url=f"/api/v1/status/{job_id}",
    )
