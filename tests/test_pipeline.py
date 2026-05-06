from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.schemas import EvaluateRequest
from app.services.pipeline import Pipeline


class FakeDownloader:
    def __init__(self, audio_path: Path) -> None:
        self.audio_path = audio_path
        self.cleaned: list[str] = []

    async def download(self, url: str, session_id: str, question_id: str) -> Path:
        return self.audio_path

    def cleanup_session(self, session_id: str) -> None:
        self.cleaned.append(session_id)

    async def close(self) -> None:
        return None


class FakeTranscription:
    async def transcribe(self, audio_path: Path) -> dict[str, str]:
        return {"transcript_text": "I would help the customer calmly."}

    async def close(self) -> None:
        return None


class FakeEvaluation:
    def __init__(self) -> None:
        self.weights_seen: list[dict[str, float]] = []

    async def evaluate_answer(self, **kwargs) -> dict:
        self.weights_seen.append(kwargs["scoring_weights"])
        return {
            "total_score": 8,
            "sentiment_breakdown": {
                "courtesy": 8,
                "empathy": 7,
                "respect": 8,
                "tone": 8,
            },
            "handling_breakdown": {
                "communication_clarity": 7,
                "engagement": 7,
                "problem_handling_approach": 8,
            },
            "strengths": ["Empathy"],
            "improvement_areas": ["More detail"],
            "final_summary": "Solid response.",
        }

    async def summarize_session(self, **kwargs) -> dict:
        return {
            "total_score": 8.0,
            "strengths": ["Empathy"],
            "weaknesses": ["More detail"],
            "overall_summary": "Good support behavior.",
        }

    async def close(self) -> None:
        return None


class FakeJobManager:
    def __init__(self) -> None:
        self.statuses: list[tuple[str, str, str | None]] = []
        self.progress_calls: list[tuple[int, int]] = []
        self.stored_results: dict | None = None

    async def update_status(self, job_id: str, status: str, message=None, **kwargs) -> None:
        self.statuses.append((job_id, status, message))

    async def increment_progress(self, job_id: str, *, transcribed: int = 0, evaluated: int = 0) -> None:
        self.progress_calls.append((transcribed, evaluated))

    async def store_results(self, job_id: str, results: dict) -> None:
        self.stored_results = results


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_merges_weights_and_cleans_up_job_directory(self) -> None:
        request = EvaluateRequest(
            session_id="session-1",
            candidate_name="Test User",
            candidate_id="cand-1",
            scoring_weights={"courtesy": 2.0},
            questions=[
                {
                    "question_id": "q1",
                    "question_text": "How do you help?",
                    "recording_url": "https://example.com/audio.mp3",
                    "standard_responses": ["Be polite"],
                }
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "audio.webm"
            audio_path.write_bytes(b"audio")

            downloader = FakeDownloader(audio_path)
            evaluation = FakeEvaluation()
            job_manager = FakeJobManager()
            pipeline = Pipeline(
                job_manager=job_manager,  # type: ignore[arg-type]
                downloader=downloader,  # type: ignore[arg-type]
                transcription=FakeTranscription(),  # type: ignore[arg-type]
                evaluation=evaluation,  # type: ignore[arg-type]
            )

            await pipeline.process_session("job-1", request)

        self.assertEqual(downloader.cleaned, ["job-1"])
        self.assertEqual(job_manager.progress_calls, [(1, 0), (0, 1)])
        self.assertIsNotNone(job_manager.stored_results)
        assert job_manager.stored_results is not None
        self.assertEqual(job_manager.stored_results["overall_score"], 8.0)
        self.assertEqual(evaluation.weights_seen[0]["courtesy"], 2.0)
        self.assertIn("communication", evaluation.weights_seen[0])
