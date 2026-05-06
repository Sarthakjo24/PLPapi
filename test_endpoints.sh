#!/bin/bash
# Quick endpoint checks for a running local server.

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
API_PREFIX="${API_PREFIX:-/api/v1}"
API_KEY="${API_KEY:-}"

echo "API Endpoint Testing"
echo "===================="
echo ""

echo "1. Testing health endpoint..."
curl -s -X GET "$BASE_URL$API_PREFIX/health" | jq .
echo ""
echo ""

echo "2. Testing API key requirement (should return 403)..."
curl -s -X GET "$BASE_URL$API_PREFIX/status/test-job-id" | jq .
echo ""
echo ""

if [[ -n "$API_KEY" ]]; then
  echo "3. Testing status endpoint with API key (should return 404)..."
  curl -s -X GET "$BASE_URL$API_PREFIX/status/nonexistent-job-id" \
    -H "X-API-Key: $API_KEY" | jq .
  echo ""
  echo ""
else
  echo "3. Skipping authenticated status test because API_KEY is not set."
  echo ""
fi

echo "4. Swagger docs: $BASE_URL/docs"
echo "5. ReDoc:       $BASE_URL/redoc"
echo ""
echo "===================="
echo "Testing complete."
