#!/bin/bash
# API Testing Script - Test all endpoints with curl

BASE_URL="http://localhost:8000"
API_KEY="sk_ozKY2x0hpTpcQ4rYV79eSFQpDTdKHQng9IoO8iQSqiC2fo9S"  # From .env

echo "🧪 API Endpoint Testing"
echo "======================="
echo ""

# 1. Health Check (No Auth Required)
echo "1️⃣  Testing Health Endpoint (No Auth)..."
curl -s -X GET "$BASE_URL/health" | jq .
echo ""
echo ""

# 2. Test API Key Authentication
echo "2️⃣  Testing API Key Requirement (Should return 403)..."
curl -s -X GET "$BASE_URL/status/test-job-id" | jq .
echo ""
echo ""

# 3. Test Status Endpoint with Valid API Key
echo "3️⃣  Testing Status Endpoint with Valid API Key (Should return 404 - Job not found)..."
curl -s -X GET "$BASE_URL/status/nonexistent-job-id" \
  -H "X-API-Key: $API_KEY" | jq .
echo ""
echo ""

# 4. Test Swagger Documentation
echo "4️⃣  Swagger Documentation available at:"
echo "    $BASE_URL/docs"
echo ""

# 5. Test ReDoc Documentation
echo "5️⃣  ReDoc Documentation available at:"
echo "    $BASE_URL/redoc"
echo ""

echo "======================="
echo "✓ Testing complete!"
echo ""
echo "📌 Next Steps:"
echo "  - Try interactive testing at $BASE_URL/docs"
echo "  - Check logs for any errors"
echo "  - Run 'python test_api.py' for full production readiness check"
