"""
Production Readiness Testing Script
Tests all critical API functionality and dependencies
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import redis

# Load settings
sys.path.insert(0, str(Path(__file__).parent))
from app.config import settings

BASE_URL = f"http://{settings.host}:{settings.port}"
API_KEY = settings.api_key


class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []

    def add_pass(self, test_name: str):
        self.passed.append(test_name)
        print(f"✓ {test_name}")

    def add_fail(self, test_name: str, error: str):
        self.failed.append((test_name, error))
        print(f"✗ {test_name}: {error}")

    def summary(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*60}")
        print(f"Results: {len(self.passed)}/{total} tests passed")
        if self.failed:
            print("\nFailed tests:")
            for test, error in self.failed:
                print(f"  - {test}: {error}")
        print(f"{'='*60}")
        return len(self.failed) == 0


async def test_health() -> TestResults:
    """Test health endpoint"""
    results = TestResults()
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/health", timeout=5)
            
            if response.status_code == 200:
                results.add_pass("Health check endpoint")
            else:
                results.add_fail("Health check", f"Status {response.status_code}")
    except Exception as e:
        results.add_fail("Health check", str(e))
    
    return results


def test_redis_connection() -> TestResults:
    """Test Redis connectivity"""
    results = TestResults()
    
    try:
        r = redis.from_url(settings.redis_url)
        r.ping()
        results.add_pass("Redis connection")
    except Exception as e:
        results.add_fail("Redis connection", str(e))
    
    return results


def test_env_variables() -> TestResults:
    """Validate critical environment variables"""
    results = TestResults()
    
    checks = [
        ("API_KEY configured", settings.api_key != "change-me-api-key"),
        ("OpenAI API key configured", settings.openai_api_key.startswith("sk-")),
        ("Redis URL valid", "redis://" in settings.redis_url),
        ("Temp directory writable", settings.effective_temp_dir.exists()),
        ("CORS origins configured", len(settings.cors_origins) > 0),
    ]
    
    for check_name, passed in checks:
        if passed:
            results.add_pass(check_name)
        else:
            results.add_fail(check_name, "Invalid or missing configuration")
    
    return results


async def test_api_endpoints() -> TestResults:
    """Test core API endpoints"""
    results = TestResults()
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Test with missing API key
            response = await client.get(f"{BASE_URL}/status/test-job-id")
            if response.status_code == 403:
                results.add_pass("API key authentication enforced")
            else:
                results.add_fail("API key validation", "Auth not enforced properly")
            
            # Test with valid API key
            headers = {"X-API-Key": settings.api_key}
            response = await client.get(
                f"{BASE_URL}/status/nonexistent-job-id",
                headers=headers,
                timeout=5
            )
            if response.status_code == 404:
                results.add_pass("Status endpoint responds correctly")
            else:
                results.add_fail("Status endpoint", f"Unexpected status {response.status_code}")
    
    except Exception as e:
        results.add_fail("API endpoints", str(e))
    
    return results


async def test_performance() -> TestResults:
    """Test API response times"""
    results = TestResults()
    
    try:
        async with httpx.AsyncClient() as client:
            start = time.time()
            response = await client.get(f"{BASE_URL}/health", timeout=5)
            elapsed = time.time() - start
            
            if elapsed < 0.5:
                results.add_pass(f"Health check response time ({elapsed:.3f}s)")
            else:
                results.add_fail("Performance", f"Slow response ({elapsed:.3f}s)")
    except Exception as e:
        results.add_fail("Performance test", str(e))
    
    return results


def print_config_summary():
    """Print configuration summary"""
    print("\n" + "="*60)
    print("API Configuration Summary")
    print("="*60)
    print(f"Environment:     {settings.environment}")
    print(f"Host:            {settings.host}:{settings.port}")
    print(f"Log Level:       {settings.log_level}")
    print(f"OpenAI Model:    {settings.openai_model}")
    print(f"Whisper:         {'faster-whisper' if settings.use_faster_whisper else 'openai-only'}")
    print(f"Redis URL:       {settings.redis_url.split('/')[-1]}")
    print(f"CORS Origins:    {', '.join(settings.cors_origins)}")
    print(f"Rate Limits:     {settings.rate_limit_evaluate} / {settings.rate_limit_status}")
    print(f"Temp Dir:        {settings.effective_temp_dir}")
    print("="*60 + "\n")


async def main():
    """Run all tests"""
    print("\n🧪 Starting Production Readiness Tests...\n")
    
    print_config_summary()
    
    all_results = []
    
    # Run tests
    print("Running configuration checks...")
    all_results.append(test_env_variables())
    
    print("\nTesting Redis connection...")
    all_results.append(test_redis_connection())
    
    print("\nTesting API health...")
    all_results.append(await test_health())
    
    print("\nTesting API endpoints...")
    all_results.append(await test_api_endpoints())
    
    print("\nTesting performance...")
    all_results.append(await test_performance())
    
    # Summary
    total_passed = sum(len(r.passed) for r in all_results)
    total_failed = sum(len(r.failed) for r in all_results)
    
    print(f"\n{'='*60}")
    print(f"FINAL RESULTS: {total_passed} passed, {total_failed} failed")
    print("="*60)
    
    if total_failed == 0:
        print("✓ API is PRODUCTION READY!\n")
        return 0
    else:
        print("✗ Fix issues before deploying to production\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
