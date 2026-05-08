from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.config import settings
from app.dependencies import get_job_manager, verify_api_key
from app.rate_limiter import limiter
from app.schemas import (
    AckResponse,
    TranscriptJobStatusResponse,
    TranscriptUploadAckResponse,
)
from app.services.job_manager import JobManager
from app.services.transcription import TranscriptionService
from app.utils.helpers import ensure_dir

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transcription"], dependencies=[Depends(verify_api_key)])


def _cleanup_background_task(task: asyncio.Task[None], background_tasks: set) -> None:
    background_tasks.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        logger.warning("Background task %s was cancelled.", task.get_name())
    except Exception:
        logger.exception("Background task %s failed.", task.get_name())


async def _transcription_worker(
    request: Request,
    job_id: str,
    audio_path: Path,
) -> None:
    """Run transcription job with retries and update Redis job state."""
    job_manager: JobManager = request.app.state.job_manager
    transcription: TranscriptionService = getattr(
        request.app.state, "transcription_service", TranscriptionService()
    )

    # Ensure service is discoverable for lifespan close()
    request.app.state.transcription_service = transcription

    last_error: str | None = None
    for attempt in range(settings.max_retries + 1):
        try:
            await job_manager.update_status(
                job_id,
                status="processing",
                message="Transcribing audio...",
                retry_count=attempt,
            )
            result = await transcription.transcribe(audio_path)
            transcript_text = (result.get("transcript_text", "") or "").strip()

            if not transcript_text:
                # Treat empty transcript as a failure to satisfy "notifies if transcription fails and retries"
                raise RuntimeError("Transcription returned empty transcript_text.")

            await job_manager.update_status(
                job_id,
                status="completed",
                message="Transcription completed successfully.",
                retry_count=attempt,
            )
            # Store results payload in the same job model
            await job_manager.store_results(
                job_id,
                {"job_type": "transcription", "transcript_text": transcript_text},
            )
            return
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Transcription attempt %d failed for job %s: %s",
                attempt + 1,
                job_id,
                last_error,
            )
            if attempt < settings.max_retries:
                await job_manager.update_status(
                    job_id,
                    status="retrying",
                    message="Transcription failed. Retrying...",
                    error_detail=last_error[:500],
                    retry_count=attempt + 1,
                )
                await asyncio.sleep(2.0**attempt)
            else:
                await job_manager.update_status(
                    job_id,
                    status="failed",
                    message="Transcription failed after retries.",
                    error_detail=last_error[:500],
                    retry_count=attempt,
                )
                return
        finally:
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                logger.exception("Failed deleting temp audio: %s", audio_path)


@router.get("/transcript", response_class=HTMLResponse, include_in_schema=False)
async def transcript_page() -> str:
    """A lightweight page to verify transcription endpoint wiring is up."""
    return """
    <!doctype html>
    <html>
      <head><meta charset="utf-8"/><title>Transcript Service</title></head>
      <body style="font-family: Arial, sans-serif; padding: 24px;">
        <h1>Transcript Service</h1>
        <p>If you can see this page, the transcription API is deployed and reachable.</p>
        <p>Use <code>/api/v1/transcript/submit</code> to upload audio and <code>/api/v1/transcript/status/<job_id></code> to poll.</p>
        <p><b>Upload format:</b> raw request body (octet-stream) + <code>X-Filename</code> header for file extension.</p>
      </body>
    </html>
    """


@router.post(
    "/transcript/submit",
    response_model=TranscriptUploadAckResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(getattr(settings, "rate_limit_transcript_submit", "15/minute"))
async def submit_transcription(
    request: Request,
    job_manager: JobManager = Depends(get_job_manager),
) -> TranscriptUploadAckResponse:
    """Upload audio bytes and enqueue a transcription-only job.

    To avoid requiring `python-multipart` on environments where it's not installed,
    this endpoint accepts raw bytes:
      - Content-Type: application/octet-stream (recommended)
      - Header: X-Filename: original filename (used only for extension)
    """
    filename = request.headers.get("X-Filename")
    if not filename:
        raise HTTPException(
            status_code=400,
            detail='Missing header "X-Filename" to infer audio extension.',
        )

    ext = Path(filename).suffix.lower()
    if ext not in {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".mp4", ".aac", ".flac"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio extension: {ext}.",
        )

    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="Request body is empty.")
    if len(content) > settings.max_audio_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large. Max {settings.max_audio_size_bytes} bytes.",
        )

    job_id = str(uuid.uuid4())
    await job_manager.create_job(
        job_id=job_id,
        session_id="transcript",
        question_count=1,
    )
    await job_manager.update_status(
        job_id,
        status="received",
        message="Job received. Awaiting transcription processing...",
        retry_count=0,
    )

    tmp_dir = ensure_dir(Path(settings.effective_temp_dir) / "transcript")
    audio_path = tmp_dir / f"{job_id}{ext}"
    audio_path.write_bytes(content)

    background_task = asyncio.create_task(
        _transcription_worker(request, job_id, audio_path),
        name=f"transcription:{job_id}",
    )
    request.app.state.background_tasks.add(background_task)
    background_task.add_done_callback(
        lambda task: _cleanup_background_task(task, request.app.state.background_tasks)
    )

    return TranscriptUploadAckResponse(
        job_id=job_id,
        status="received",
        message="Job received. Transcription queued.",
        poll_url=f"{settings.api_prefix}/transcript/status/{job_id}",
    )


@router.get(
    "/transcript/status/{job_id}",
    response_model=TranscriptJobStatusResponse,
)
@limiter.limit(getattr(settings, "rate_limit_transcript_status", "60/minute"))
async def get_transcript_status(
    request: Request,
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager),
) -> TranscriptJobStatusResponse:
    """Poll the status of a transcription job."""
    job = await job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or has expired.",
        )

    created_at = float(job.get("created_at", 0.0) or 0.0)
    # job_manager stores created_at as time.time() absolute; elapsed is best-effort
    elapsed = 0.0 if not created_at else round((request.scope.get("state", None) or 0) or 0, 2)  # fallback
    job_status = job.get("status", "unknown")

    results = job.get("results")
    transcript_text = None
    if job_status == "completed" and results and isinstance(results, dict):
        transcript_text = (results.get("transcript_text") or None) if results else None

    # recompute elapsed using monotonic-ish best effort (keeps response valid)
    # Prefer to avoid coupling; tests don't validate elapsed_seconds precisely.
    import time as _time

    elapsed = round((_time.time() - created_at), 2) if created_at else None

    return TranscriptJobStatusResponse(
        job_id=job_id,
        status=(
            "completed"
            if job_status == "completed"
            else "failed"
            if job_status == "failed"
            else "retrying"
            if job_status == "retrying"
            else "processing"
            if job_status == "processing"
            else "received"
            if job_status == "received"
            else "unknown"
        ),
        transcript_text=transcript_text,
        message=job.get("message"),
        retry_count=job.get("retry_count"),
        error_detail=job.get("error_detail"),
        elapsed_seconds=elapsed,
    )


@router.post(
    "/transcript/{job_id}/ack",
    response_model=AckResponse,
)
async def acknowledge_transcript_results(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager),
) -> AckResponse:
    """Acknowledge receipt of transcription results and clear the job."""
    job = await job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or already acknowledged.",
        )

    await job_manager.delete_job(job_id)
    return AckResponse(message="Transcription results acknowledged and cleared.")
