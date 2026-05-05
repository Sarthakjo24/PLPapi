from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import verify_api_key
from app.schemas import AckResponse, JobStatusResponse, QuestionResult
from app.services.job_manager import JobManager

router = APIRouter(tags=["status"], dependencies=[Depends(verify_api_key)])
limiter = Limiter(key_func=get_remote_address)

_job_manager = JobManager()


@router.get("/status/{job_id}", response_model=JobStatusResponse)
@limiter.limit(settings.rate_limit_status)
async def get_job_status(request: Request, job_id: str) -> JobStatusResponse:
    """Poll the status of an evaluation job.

    Returns progress while processing and full results when completed.
    """
    job = await _job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or has expired.",
        )

    created_at = job.get("created_at", time.time())
    elapsed = round(time.time() - created_at, 2)
    job_status = job.get("status", "unknown")

    # ── Completed: include full results ──
    if job_status == "completed" and job.get("results"):
        results = job["results"]
        question_results = [
            QuestionResult(**qr) for qr in results.get("question_results", [])
        ]
        return JobStatusResponse(
            job_id=job_id,
            status="completed",
            session_id=results.get("session_id"),
            processing_time_seconds=results.get("processing_time_seconds"),
            elapsed_seconds=elapsed,
            message="Evaluation completed successfully.",
            overall_score=results.get("overall_score"),
            overall_summary=results.get("overall_summary"),
            overall_strengths=results.get("overall_strengths"),
            overall_weaknesses=results.get("overall_weaknesses"),
            question_results=question_results,
        )

    # ── In-progress / retrying / failed ──
    return JobStatusResponse(
        job_id=job_id,
        status=job_status,
        session_id=job.get("session_id"),
        progress=job.get("progress"),
        elapsed_seconds=elapsed,
        message=job.get("message"),
        retry_count=job.get("retry_count"),
        error_detail=job.get("error_detail"),
    )


@router.post("/results/{job_id}/ack", response_model=AckResponse)
async def acknowledge_results(job_id: str) -> AckResponse:
    """Acknowledge receipt of results. Deletes the job from Redis cache."""
    job = await _job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or already acknowledged.",
        )

    await _job_manager.delete_job(job_id)
    return AckResponse(message="Results acknowledged and cleared.")
