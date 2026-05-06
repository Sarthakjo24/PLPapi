from __future__ import annotations

import unittest

from app.utils.helpers import (
    coerce_list_points,
    coerce_numeric,
    extract_json_object,
    normalize_transcript,
)


class HelperTests(unittest.TestCase):
    def test_extract_json_object_handles_markdown_fence(self) -> None:
        payload = extract_json_object('```json\n{"score": 8, "ok": true}\n```')
        self.assertEqual(payload["score"], 8)
        self.assertTrue(payload["ok"])

    def test_coerce_numeric_supports_strings(self) -> None:
        self.assertEqual(coerce_numeric("score: 7.5/10"), 7.5)
        self.assertIsNone(coerce_numeric(""))

    def test_coerce_list_points_normalizes_text(self) -> None:
        value = coerce_list_points("1. Empathy\n2. Clarity")
        self.assertEqual(value, ["Empathy", "Clarity"])

    def test_normalize_transcript_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_transcript(" hello \n world\t"), "hello world")
