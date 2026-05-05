# API Testing Script for Windows PowerShell
# Test all endpoints quickly

$BASE_URL = "http://localhost:8000"
$API_KEY = "sk_ozKY2x0hpTpcQ4rYV79eSFQpDTdKHQng9IoO8iQSqiC2fo9S"

Write-Host "🧪 API Endpoint Testing" -ForegroundColor Cyan
Write-Host "=======================" -ForegroundColor Cyan
Write-Host ""

# 1. Health Check
Write-Host "1️⃣  Testing Health Endpoint (No Auth)..." -ForegroundColor Green
try {
    $response = Invoke-RestMethod -Uri "$BASE_URL/health" -Method Get
    $response | ConvertTo-Json | Write-Host
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
}
Write-Host ""

# 2. Test Missing API Key (should fail)
Write-Host "2️⃣  Testing API Key Requirement (Should return 403)..." -ForegroundColor Green
try {
    $response = Invoke-RestMethod -Uri "$BASE_URL/status/test-job-id" -Method Get -ErrorAction Stop
    $response | ConvertTo-Json | Write-Host
} catch {
    if ($_.Exception.Response.StatusCode -eq 403) {
        Write-Host "✓ Correctly rejected request without API key" -ForegroundColor Green
    } else {
        Write-Host "Response: $($_.Exception.Response.StatusCode)" -ForegroundColor Yellow
    }
}
Write-Host ""

# 3. Test Status with Valid API Key
Write-Host "3️⃣  Testing Status Endpoint with Valid API Key..." -ForegroundColor Green
try {
    $headers = @{ "X-API-Key" = $API_KEY }
    $response = Invoke-RestMethod -Uri "$BASE_URL/status/nonexistent-job" `
        -Method Get `
        -Headers $headers `
        -ErrorAction Stop
    $response | ConvertTo-Json | Write-Host
} catch {
    if ($_.Exception.Response.StatusCode -eq 404) {
        Write-Host "✓ Correctly returned 404 (Job not found)" -ForegroundColor Green
    } else {
        Write-Host "Response: $($_.Exception.Response.StatusCode) - $_" -ForegroundColor Yellow
    }
}
Write-Host ""

# 4. Print URLs
Write-Host "📚 Documentation URLs:" -ForegroundColor Cyan
Write-Host "  Swagger UI:  $BASE_URL/docs" -ForegroundColor White
Write-Host "  ReDoc:       $BASE_URL/redoc" -ForegroundColor White
Write-Host ""

Write-Host "=======================" -ForegroundColor Cyan
Write-Host "✓ Testing complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📌 Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Open $BASE_URL/docs in browser for interactive testing"
Write-Host "  2. Run 'python test_api.py' for production readiness check"
Write-Host "  3. Check 'PRODUCTION_READY.md' for full checklist"
