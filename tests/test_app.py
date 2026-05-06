from __future__ import annotations

import logging
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.config import settings as global_settings
from app.error_handlers import register_error_handlers
from app.main import create_app
from app.logging_config import DevFormatter, JSONFormatter, setup_logging


class FakeJobManager:
    def __init__(self) -> None:
        self.jobs = {
            "completed-job": {
                "created_at": time.time(),
                "status": "completed",
                "results": {
                    "session_id": "session-1",
                    "processing_time_seconds": 1.5,
                    "overall_score": 8.0,
                    "overall_summary": "Good support behavior.",
                    "overall_strengths": ["Empathy"],
                    "overall_weaknesses": ["More detail"],
                    "question_results": [
                        {
                            "question_id": "q1",
                            "transcript": "Hello there",
                            "total_score": 8.0,
                            "courtesy_score": 8.0,
                            "empathy_score": 7.0,
                            "respect_score": 8.0,
                            "tone_score": 8.0,
                            "communication_score": 7.0,
                            "strengths": ["Empathy"],
                            "improvement_areas": ["More detail"],
                            "summary": "Solid response.",
                        }
                    ],
                },
            }
        }
        self.created_jobs: list[tuple[str, str, int]] = []
        self.deleted_jobs: list[str] = []

    async def ping(self) -> bool:
        return True

    async def get_job(self, job_id: str):
        return self.jobs.get(job_id)

    async def create_job(self, job_id: str, session_id: str, question_count: int):
        self.created_jobs.append((job_id, session_id, question_count))
        self.jobs[job_id] = {
            "created_at": time.time(),
            "status": "received",
            "session_id": session_id,
            "progress": f"0/{question_count} evaluated",
            "retry_count": 0,
            "message": "Job received.",
            "results": None,
            "error_detail": None,
        }

    async def delete_job(self, job_id: str) -> bool:
        self.deleted_jobs.append(job_id)
        self.jobs.pop(job_id, None)
        return True

    async def close(self) -> None:
        return None


class FakePipeline:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def process_session(self, job_id, payload) -> None:
        self.calls.append((job_id, payload.session_id))

    async def close(self) -> None:
        return None


class AppRouteTests(unittest.TestCase):
    def build_client(self) -> tuple[TestClient, FakeJobManager, FakePipeline]:
        app = create_app()
        fake_job_manager = FakeJobManager()
        fake_pipeline = FakePipeline()
        app.state.job_manager = fake_job_manager
        app.state.pipeline = fake_pipeline
        app.state.background_tasks = set()

        environment_patch = patch.object(global_settings, "environment", "test")
        api_key_patch = patch.object(global_settings, "api_key", "test-api-key")
        environment_patch.start()
        api_key_patch.start()
        self.addCleanup(api_key_patch.stop)
        self.addCleanup(environment_patch.stop)
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client, fake_job_manager, fake_pipeline

    def test_docs_and_openapi_are_enabled(self) -> None:
        client, _, _ = self.build_client()
        self.assertEqual(client.get("/docs").status_code, 200)
        self.assertEqual(client.get("/redoc").status_code, 200)
        schema = client.get("/openapi.json")
        self.assertEqual(schema.status_code, 200)
        self.assertIn("/api/v1/evaluate", schema.json()["paths"])

    def test_health_endpoint_uses_app_state_job_manager(self) -> None:
        client, _, _ = self.build_client()
        response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["dependencies"]["redis"], "ok")

    def test_status_requires_api_key(self) -> None:
        client, _, _ = self.build_client()
        response = client.get("/api/v1/status/missing-job")
        self.assertEqual(response.status_code, 403)

    def test_status_and_ack_endpoints_work(self) -> None:
        client, fake_job_manager, _ = self.build_client()
        headers = {"X-API-Key": "test-api-key"}

        response = client.get("/api/v1/status/completed-job", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")

        ack = client.post("/api/v1/results/completed-job/ack", headers=headers)
        self.assertEqual(ack.status_code, 200)
        self.assertIn("completed-job", fake_job_manager.deleted_jobs)

    def test_evaluate_endpoint_queues_background_pipeline(self) -> None:
        client, fake_job_manager, fake_pipeline = self.build_client()
        headers = {"X-API-Key": "test-api-key"}

        response = client.post(
            "/api/v1/evaluate",
            headers=headers,
            json={
                "session_id": "session-1",
                "candidate_name": "Test User",
                "candidate_id": "cand-1",
                "questions": [
                    {
                        "question_id": "q1",
                        "question_text": "How do you help?",
                        "recording_url": "https://example.com/audio.mp3",
                        "standard_responses": ["Be polite"],
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(fake_job_manager.created_jobs), 1)
        time.sleep(0.05)
        self.assertEqual(len(fake_pipeline.calls), 1)
        self.assertTrue(response.json()["poll_url"].startswith("/api/v1/status/"))

    def test_invalid_payload_returns_validation_error(self) -> None:
        client, _, _ = self.build_client()
        headers = {"X-API-Key": "test-api-key"}

        response = client.post(
            "/api/v1/evaluate",
            headers=headers,
            json={
                "session_id": "session-1",
                "candidate_name": "Test User",
                "candidate_id": "cand-1",
                "questions": [
                    {
                        "question_id": "q1",
                        "question_text": "",
                        "recording_url": "https://example.com/audio.mp3",
                        "standard_responses": ["Be polite"],
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "Validation error")


class LoggingAndErrorHandlerTests(unittest.TestCase):
    def test_setup_logging_switches_formatters(self) -> None:
        setup_logging("INFO", "prod")
        self.assertIsInstance(logging.getLogger().handlers[0].formatter, JSONFormatter)
        setup_logging("INFO", "dev")
        self.assertIsInstance(logging.getLogger().handlers[0].formatter, DevFormatter)

    def test_unhandled_errors_hide_details_in_prod(self) -> None:
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/boom")
        async def boom() -> None:
            raise RuntimeError("secret detail")

        with patch.object(global_settings, "environment", "prod"):
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/boom")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"],
            "Internal server error. Please try again later.",
        )

    def test_http_exception_uses_standard_error_shape(self) -> None:
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/missing")
        async def missing() -> None:
            raise HTTPException(status_code=404, detail="Nope")

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Nope")
