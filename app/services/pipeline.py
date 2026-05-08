from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config import settings
from app.schemas import EvaluateRequest
from app.services.evaluation import EvaluationService
from app.services.job_manager import JobManager
from app.schemas import QuestionPayload

logger = logging.getLogger(__name__)


class Pipeline:
    """Session pipeline: evaluate using transcript_text supplied by the frontend.

    Transcription is intentionally decoupled into /api/v1/transcript.
    """

    def __init__(
        self,
        job_manager: JobManager,
        downloader: Any | None = None,
        transcription: Any | None = None,
        evaluation: EvaluationService | None = None,
    ) -> None:
        # downloader/transcription are accepted for backward compatibility.
        # Evaluation no longer downloads/transcribes, but we still honor cleanup
        # for callers/tests that inject a downloader.
        _ = transcription
        self.jobs = job_manager
        self.downloader = downloader
        self.evaluation = evaluation or EvaluationService()

    async def process_session(self, job_id: str, request: EvaluateRequest) -> None:
        """Run evaluation pipeline with retry semantics for the whole session."""
        retry_count = 0
        while retry_count <= settings.max_retries:
            try:
                await self._run(job_id, request, retry_count)
                return
            except Exception as exc:
                retry_count += 1
                if retry_count <= settings.max_retries:
                    logger.warning(
                        "Pipeline attempt %d failed for job %s: %s; retrying",
                        retry_count,
                        job_id,
                        exc,
                    )
                    await self.jobs.update_status(
                        job_id,
                        status="retrying",
                        message=(
                            "Evaluation encountered an error. Retrying automatically "
                            f"(attempt {retry_count + 1}/{settings.max_retries + 1})."
                        ),
                        retry_count=retry_count,
                    )
                    await asyncio.sleep(2.0**retry_count)
                else:
                    logger.error("Pipeline exhausted retries for job %s: %s", job_id, exc)
                    await self.jobs.update_status(
                        job_id,
                        status="failed",
                        message=(
                            f"Evaluation failed after {settings.max_retries + 1} attempts. "
                            f"Error: {type(exc).__name__}"
                        ),
                        error_detail=str(exc)[:500],
                        retry_count=retry_count,
                    )
            finally:
                if self.downloader is not None and hasattr(self.downloader, "cleanup_session"):
                    try:
                        self.downloader.cleanup_session(job_id)
                    except Exception:
                        logger.exception("Downloader cleanup_session failed for job %s", job_id)

    async def _run(
        self, job_id: str, request: EvaluateRequest, retry_count: int
    ) -> None:
        start_time = time.time()
        scoring_weights = {**settings.scoring_weights, **(request.scoring_weights or {})}

        await self.jobs.update_status(
            job_id,
            status="processing",
            message="Evaluating transcripts...",
            retry_count=retry_count,
        )

        tasks = [
            self._process_single_question(
                job_id=job_id,
                question=question,
                module_title=request.module_title,
                scoring_weights=scoring_weights,
            )
            for question in request.questions
        ]
        question_results = await asyncio.gather(*tasks)

        evaluated_for_summary = [
            {
                "question_id": result["question_id"],
                "total_score": result["total_score"],
                "strengths": result["strengths"],
                "improvement_areas": result["improvement_areas"],
                "transcript_excerpt": (result.get("transcript") or "")[:400],
            }
            for result in question_results
            if result.get("total_score") is not None
        ]

        overall = await self.evaluation.summarize_session(
            module_title=request.module_title,
            candidate_name=request.candidate_name,
            candidate_id=request.candidate_id,
            evaluated_answers=evaluated_for_summary,
        )

        elapsed = round(time.time() - start_time, 2)
        results: dict[str, Any] = {
            "session_id": request.session_id,
            "candidate_name": request.candidate_name,
            "candidate_id": request.candidate_id,
            "processing_time_seconds": elapsed,
            "overall_score": overall.get("total_score"),
            "overall_summary": overall.get("overall_summary"),
            "overall_strengths": overall.get("strengths"),
            "overall_weaknesses": overall.get("weaknesses"),
            "question_results": question_results,
        }

        await self.jobs.store_results(job_id, results)
        logger.info("Pipeline completed for job %s in %.1fs", job_id, elapsed)

    async def _process_single_question(
        self,
        job_id: str,
        question: QuestionPayload,
        module_title: str,
        scoring_weights: dict[str, float],
    ) -> dict[str, Any]:
        """Evaluate a single question using transcript_text supplied by frontend."""
        transcript_text = str(question.transcript_text or "").strip()

        # Preserve legacy progress semantics: transcription is now "already done" by frontend.
        await self.jobs.increment_progress(job_id, transcribed=1)

        evaluation_result = await self.evaluation.evaluate_answer(
            question_text=question.question_text,
            transcript_text=transcript_text,
            standard_responses=question.standard_responses,
            module_title=module_title,
            scoring_weights=scoring_weights,
        )
        await self.jobs.increment_progress(job_id, evaluated=1)

        sentiment = evaluation_result.get("sentiment_breakdown") or {}
        handling = evaluation_result.get("handling_breakdown") or {}

        return {
            "question_id": question.question_id,
            "transcript": transcript_text,
            "total_score": float(evaluation_result.get("total_score") or 0),
            "courtesy_score": float(sentiment.get("courtesy") or 0),
            "empathy_score": float(sentiment.get("empathy") or 0),
            "respect_score": float(sentiment.get("respect") or 0),
            "tone_score": float(sentiment.get("tone") or 0),
            "communication_score": float(handling.get("communication_clarity") or 0),
            "strengths": evaluation_result.get("strengths", []),
            "improvement_areas": evaluation_result.get("improvement_areas", []),
            "summary": str(evaluation_result.get("final_summary") or ""),
        }

    async def close(self) -> None:
        """Close pipeline dependencies."""
        await self.evaluation.close()
