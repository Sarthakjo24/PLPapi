from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app.config import settings
from app.services.audio_downloader import AudioDownloader
from app.services.evaluation import EvaluationService
from app.services.job_manager import JobManager
from app.services.transcription import TranscriptionService


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.closed = False

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        return int(self.store.pop(key, None) is not None)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self.closed = True


class JobManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_job_lifecycle_and_progress_tracking(self) -> None:
        manager = JobManager(redis_client=FakeRedis())
        await manager.create_job("job-1", "session-1", 2)

        await asyncio.gather(
            manager.increment_progress("job-1", transcribed=1),
            manager.increment_progress("job-1", evaluated=1),
        )
        await manager.update_status("job-1", "processing", message="Working")
        await manager.store_results("job-1", {"question_results": []})

        job = await manager.get_job("job-1")
        assert job is not None
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["evaluated"], 1)
        self.assertEqual(job["transcribed"], 1)
        self.assertEqual(job["progress"], "1/2 evaluated")
        self.assertTrue(await manager.ping())

        deleted = await manager.delete_job("job-1")
        self.assertTrue(deleted)
        await manager.close()
        self.assertTrue(manager._redis is None)


class AudioDownloaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_streams_file_and_cleanup_removes_directory(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-length": "4"},
                content=b"data",
                request=request,
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with tempfile.TemporaryDirectory() as tmpdir:
                downloader = AudioDownloader(temp_dir=Path(tmpdir), client=client)
                path = await downloader.download(
                    "https://example.com/audio.webm",
                    "session-1",
                    "question-1",
                )
                self.assertTrue(path.exists())
                self.assertEqual(path.read_bytes(), b"data")
                downloader.cleanup_session("session-1")
                self.assertFalse(path.parent.exists())

    async def test_download_enforces_size_limit(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-length": "20"},
                content=b"0123456789",
                request=request,
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with tempfile.TemporaryDirectory() as tmpdir:
                downloader = AudioDownloader(temp_dir=Path(tmpdir), client=client)
                with patch.object(settings, "max_audio_size_bytes", 5):
                    with self.assertRaises(ValueError):
                        await downloader.download(
                            "https://example.com/audio.webm",
                            "session-1",
                            "question-1",
                        )


class TranscriptionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_transcribe_uses_openai_fallback_when_whisper_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "audio.webm"
            audio_path.write_bytes(b"audio")

            service = TranscriptionService()
            service._openai = object()  # type: ignore[assignment]
            service._run_subprocess = lambda path: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]
            service._transcribe_openai = AsyncMock(  # type: ignore[method-assign]
                return_value={"transcript_text": " Hello  world ", "detected_language": "en"}
            )

            with patch.object(settings, "use_faster_whisper", True):
                payload = await service.transcribe(audio_path)

            self.assertEqual(payload["transcript_text"], "Hello world")

    async def test_postprocess_filters_non_latin_text(self) -> None:
        service = TranscriptionService()
        payload = service._postprocess(
            {"transcript_text": "नमस्ते", "detected_language": "hi"}
        )
        self.assertEqual(payload["transcript_text"], "")


class EvaluationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_blank_transcript_returns_deterministic_result(self) -> None:
        service = EvaluationService()
        result = await service.evaluate_answer(
            question_text="How do you help?",
            transcript_text="   ",
            standard_responses=["Be polite"],
            module_title="Support",
            scoring_weights={"courtesy": 1.0},
        )
        self.assertEqual(result["total_score"], 0.0)
        self.assertTrue(result["improvement_areas"])

    async def test_summarize_session_uses_heuristic_without_client(self) -> None:
        service = EvaluationService()
        service._client = None
        result = await service.summarize_session(
            module_title="Support",
            candidate_name="Test User",
            candidate_id="cand-1",
            evaluated_answers=[
                {
                    "question_id": "q1",
                    "total_score": 8,
                    "strengths": ["Empathy"],
                    "improvement_areas": ["Clarity"],
                }
            ],
        )
        self.assertEqual(result["total_score"], 8.0)
        self.assertIn("Empathy", result["strengths"])

    def test_normalize_payload_maps_alternate_fields(self) -> None:
        service = EvaluationService()
        payload = service._normalize_payload(
            {
                "score": "7.5",
                "courtesy_score": "8",
                "communication_score": "7",
                "strengths": "1. Empathy",
                "weakness": "1. Clarity",
                "feedback": "Helpful response",
            }
        )
        self.assertEqual(payload["total_score"], 7.5)
        self.assertEqual(payload["sentiment_breakdown"]["courtesy"], 8.0)
        self.assertEqual(payload["handling_breakdown"]["communication_clarity"], 7.0)
        self.assertEqual(payload["final_summary"], "Helpful response")
