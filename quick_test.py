#!/usr/bin/env python
"""Quick API test to verify all endpoints are working"""

import httpx
import json

BASE_URL = "http://localhost:8000"
API_KEY = "sk_ozKY2x0hpTpcQ4rYV79eSFQpDTdKHQng9IoO8iQSqiC2fo9S"

def test_health():
    """Test health endpoint"""
    print("\n1️⃣  Testing Health Endpoint...")
    try:
        response = httpx.get(f"{BASE_URL}/api/v1/health")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_evaluate():
    """Test evaluate endpoint"""
    print("\n2️⃣  Testing Evaluate Endpoint (POST)...")
    payload = {
        "session_id": "test-session-1",
        "candidate_name": "John Doe",
        "candidate_id": "cand-001",
        "questions": [
            {
                "question_id": "q1",
                "question_text": "How would you handle a customer complaint?",
                "recording_url": "http://example.com/audio1.mp3",
                "standard_responses": ["Be polite", "Listen carefully"]
            }
        ]
    }
    
    try:
        response = httpx.post(
            f"{BASE_URL}/api/v1/evaluate",
            json=payload,
            headers={"X-API-Key": API_KEY}
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 202
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_auth_required():
    """Test that endpoints require API key"""
    print("\n3️⃣  Testing API Key Authentication...")
    try:
        response = httpx.get(f"{BASE_URL}/api/v1/status/test-job-id")
        print(f"   Status (no auth): {response.status_code}")
        if response.status_code == 403:
            print("   ✓ Correctly rejected request without API key")
            return True
        else:
            print(f"   ❌ Should have returned 403, got {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 API Endpoint Tests")
    print("=" * 50)
    
    results = []
    results.append(("Health Check", test_health()))
    results.append(("Evaluate Endpoint", test_evaluate()))
    results.append(("Auth Required", test_auth_required()))
    
    print("\n" + "=" * 50)
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed\n")
    
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")
