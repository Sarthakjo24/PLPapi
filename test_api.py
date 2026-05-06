"""Lightweight API smoke test for a running server."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from app.config import settings

BASE_URL = f"http://127.0.0.1:{settings.port}"
API_PREFIX = settings.api_prefix
API_KEY = settings.api_key


class TestResults:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def add_pass(self, test_name: str) -> None:
        self.passed.append(test_name)
        print(f"[PASS] {test_name}")

    def add_fail(self, test_name: str, error: str) -> None:
        self.failed.append((test_name, error))
        print(f"[FAIL] {test_name}: {error}")


async def test_health(client: httpx.AsyncClient, results: TestResults) -> None:
    response = await client.get(f"{BASE_URL}{API_PREFIX}/health")
    if response.status_code == 200:
        results.add_pass("Health endpoint")
    else:
        results.add_fail("Health endpoint", f"Unexpected status {response.status_code}")


async def test_docs(client: httpx.AsyncClient, results: TestResults) -> None:
    response = await client.get(f"{BASE_URL}{settings.docs_url}")
    if response.status_code == 200:
        results.add_pass("Swagger docs")
    else:
        results.add_fail("Swagger docs", f"Unexpected status {response.status_code}")

    response = await client.get(f"{BASE_URL}{settings.redoc_url}")
    if response.status_code == 200:
        results.add_pass("ReDoc docs")
    else:
        results.add_fail("ReDoc docs", f"Unexpected status {response.status_code}")


async def test_auth(client: httpx.AsyncClient, results: TestResults) -> None:
    response = await client.get(f"{BASE_URL}{API_PREFIX}/status/test-job-id")
    if response.status_code == 403:
        results.add_pass("API key authentication")
    else:
        results.add_fail("API key authentication", f"Unexpected status {response.status_code}")


async def test_status(client: httpx.AsyncClient, results: TestResults) -> None:
    response = await client.get(
        f"{BASE_URL}{API_PREFIX}/status/nonexistent-job-id",
        headers={"X-API-Key": API_KEY},
    )
    if response.status_code == 404:
        results.add_pass("Status endpoint")
    else:
        results.add_fail("Status endpoint", f"Unexpected status {response.status_code}")


async def test_performance(client: httpx.AsyncClient, results: TestResults) -> None:
    start = time.perf_counter()
    response = await client.get(f"{BASE_URL}{API_PREFIX}/health")
    elapsed = time.perf_counter() - start
    if response.status_code == 200 and elapsed < 1.0:
        results.add_pass(f"Health response time ({elapsed:.3f}s)")
    else:
        results.add_fail("Health response time", f"{elapsed:.3f}s")


async def main() -> int:
    print("Starting API smoke tests...\n")
    results = TestResults()

    async with httpx.AsyncClient(timeout=10) as client:
        await test_health(client, results)
        await test_docs(client, results)
        await test_auth(client, results)
        await test_status(client, results)
        await test_performance(client, results)

    total = len(results.passed) + len(results.failed)
    print(f"\nResults: {len(results.passed)}/{total} passed")
    for name, error in results.failed:
        print(f" - {name}: {error}")

    return 0 if not results.failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
