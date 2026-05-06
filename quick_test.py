#!/usr/bin/env python
"""Quick API smoke test for a running local server."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from app.config import settings

BASE_URL = f"http://127.0.0.1:{settings.port}"
API_PREFIX = settings.api_prefix
API_KEY = settings.api_key


def test_health() -> bool:
    print("\n1. Testing health endpoint...")
    try:
        response = httpx.get(f"{BASE_URL}{API_PREFIX}/health", timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        return response.status_code == 200
    except Exception as exc:
        print(f"   Error: {exc}")
        return False


def test_evaluate() -> bool:
    print("\n2. Testing evaluate endpoint...")
    payload = {
        "session_id": "test-session-1",
        "candidate_name": "John Doe",
        "candidate_id": "cand-001",
        "questions": [
            {
                "question_id": "q1",
                "question_text": "How would you handle a customer complaint?",
                "recording_url": "https://example.com/audio1.mp3",
                "standard_responses": ["Be polite", "Listen carefully"],
            }
        ],
    }

    try:
        response = httpx.post(
            f"{BASE_URL}{API_PREFIX}/evaluate",
            json=payload,
            headers={"X-API-Key": API_KEY},
            timeout=10,
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 202
    except Exception as exc:
        print(f"   Error: {exc}")
        return False


def test_auth_required() -> bool:
    print("\n3. Testing API key authentication...")
    try:
        response = httpx.get(f"{BASE_URL}{API_PREFIX}/status/test-job-id", timeout=5)
        print(f"   Status (no auth): {response.status_code}")
        if response.status_code == 403:
            print("   Correctly rejected request without API key")
            return True
        print(f"   Expected 403, got {response.status_code}")
        return False
    except Exception as exc:
        print(f"   Error: {exc}")
        return False


if __name__ == "__main__":
    print("API endpoint quick test")
    print("=" * 50)

    results = [
        ("Health check", test_health()),
        ("Evaluate endpoint", test_evaluate()),
        ("Auth required", test_auth_required()),
    ]

    print("\n" + "=" * 50)
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed\n")

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {status} {name}")
