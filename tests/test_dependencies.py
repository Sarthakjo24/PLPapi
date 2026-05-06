from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.config import settings as global_settings
from app.dependencies import verify_api_key
from app.schemas import EvaluateRequest


class DependencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_verify_api_key_accepts_valid_key(self) -> None:
        with patch.object(global_settings, "api_key", "expected-key"):
            value = await verify_api_key("expected-key")
        self.assertEqual(value, "expected-key")

    async def test_verify_api_key_rejects_invalid_key(self) -> None:
        with patch.object(global_settings, "api_key", "expected-key"):
            with self.assertRaises(HTTPException) as ctx:
                await verify_api_key("wrong-key")
        self.assertEqual(ctx.exception.status_code, 403)


class SchemaTests(unittest.TestCase):
    def test_evaluate_request_rejects_blank_standard_responses(self) -> None:
        with self.assertRaises(ValidationError):
            EvaluateRequest(
                session_id="session-1",
                candidate_name="Test User",
                candidate_id="cand-1",
                questions=[
                    {
                        "question_id": "q1",
                        "question_text": "How do you help?",
                        "recording_url": "https://example.com/audio.mp3",
                        "standard_responses": ["   "],
                    }
                ],
            )

    def test_partial_scoring_weights_are_allowed(self) -> None:
        payload = EvaluateRequest(
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
        self.assertEqual(payload.scoring_weights, {"courtesy": 2.0})
