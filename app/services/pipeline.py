from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config import settings
from app.schemas import EvaluateRequest, QuestionPayload
from app.services.audio_downloader import AudioDownloader
from app.services.evaluation import EvaluationService
from app.services.job_manager import JobManager
from app.services.transcription import TranscriptionService

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates download → transcribe → evaluate → store for a full session.

    Processes all questions concurrently for maximum speed.
    Each question is pipelined: download → transcribe → evaluate runs as a
    single chain, and all chains run in parallel.
    """

    def __init__(
        self,
        job_manager: JobManager,
        downloader: AudioDownloader | None = None,
        transcription: TranscriptionService | None = None,
        evaluation: EvaluationService | None = None,
    ) -> None:
        self.jobs = job_manager
        self.downloader = downloader or AudioDownloader()
        self.transcription = transcription or TranscriptionService()
        self.evaluation = evaluation or EvaluationService()

    async def process_session(self, job_id: str, request: EvaluateRequest) -> None:
        """Run the full evaluation pipeline. Called as a background task."""
        retry_count = 0
        while retry_count <= settings.max_retries:
            try:
                await self._run(job_id, request, retry_count)
                return  # success
            except Exception as exc:
                retry_count += 1
                if retry_count <= settings.max_retries:
                    logger.warning(
                        "Pipeline attempt %d failed for job %s: %s — retrying",
                        retry_count,
                        job_id,
                        exc,
                    )
                    await self.jobs.update_status(
                        job_id,
                        status="retrying",
                        message=(
                            f"Evaluation encountered an error. Retrying automatically "
                            f"(attempt {retry_count + 1}/{settings.max_retries + 1})."
                        ),
                        retry_count=retry_count,
                    )
                    await asyncio.sleep(2.0 ** retry_count)
                else:
                    logger.error(
                        "Pipeline exhausted retries for job %s: %s", job_id, exc
                    )
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
                self.downloader.cleanup_session(request.session_id)

    async def _run(
        self, job_id: str, request: EvaluateRequest, retry_count: int
    ) -> None:
        start_time = time.time()
        scoring_weights = request.scoring_weights or settings.scoring_weights

        await self.jobs.update_status(
            job_id,
            status="processing",
            message="Downloading and processing audio recordings...",
            retry_count=retry_count,
        )

        # ── Process all questions concurrently ──
        tasks = [
            self._process_single_question(
                job_id=job_id,
                question=q,
                module_title=request.module_title,
                scoring_weights=scoring_weights,
                question_index=i,
                total_questions=len(request.questions),
            )
            for i, q in enumerate(request.questions)
        ]
        question_results = await asyncio.gather(*tasks)

        # ── Generate overall summary ──
        evaluated_for_summary = [
            {
                "question_id": r["question_id"],
                "total_score": r["total_score"],
                "strengths": r["strengths"],
                "improvement_areas": r["improvement_areas"],
                "transcript_excerpt": r["transcript"][:400],
            }
            for r in question_results
            if r.get("total_score") is not None
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
        logger.info(
            "Pipeline completed for job %s in %.1fs", job_id, elapsed
        )

    async def _process_single_question(
        self,
        job_id: str,
        question: QuestionPayload,
        module_title: str,
        scoring_weights: dict[str, float],
        question_index: int,
        total_questions: int,
    ) -> dict[str, Any]:
        """Download → transcribe → evaluate a single question."""

        # 1. Download audio
        audio_path = await self.downloader.download(
            url=question.recording_url,
            session_id=job_id,
            question_id=question.question_id,
        )

        # 2. Transcribe
        transcription_result = await self.transcription.transcribe(audio_path)
        transcript_text = transcription_result.get("transcript_text", "")

        # Update progress: transcribed
        await self.jobs.update_progress(
            job_id, transcribed=question_index + 1
        )

        # 3. Evaluate with OpenAI
        eval_result = await self.evaluation.evaluate_answer(
            question_text=question.question_text,
            transcript_text=transcript_text,
            standard_responses=question.standard_responses,
            module_title=module_title,
            scoring_weights=scoring_weights,
        )

        # Update progress: evaluated
        await self.jobs.update_progress(
            job_id, evaluated=question_index + 1
        )

        # 4. Build result
        sentiment = eval_result.get("sentiment_breakdown") or {}
        handling = eval_result.get("handling_breakdown") or {}

        return {
            "question_id": question.question_id,
            "transcript": transcript_text,
            "total_score": float(eval_result.get("total_score") or 0),
            "courtesy_score": float(sentiment.get("courtesy") or 0),
            "empathy_score": float(sentiment.get("empathy") or 0),
            "respect_score": float(sentiment.get("respect") or 0),
            "tone_score": float(sentiment.get("tone") or 0),
            "communication_score": float(
                handling.get("communication_clarity") or 0
            ),
            "strengths": eval_result.get("strengths", []),
            "improvement_areas": eval_result.get("improvement_areas", []),
            "summary": str(eval_result.get("final_summary") or ""),
        }
