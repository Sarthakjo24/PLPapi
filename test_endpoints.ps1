# Quick endpoint checks for a running local server.

$BASE_URL = if ($env:BASE_URL) { $env:BASE_URL } else { "http://127.0.0.1:8000" }
$API_PREFIX = if ($env:API_PREFIX) { $env:API_PREFIX } else { "/api/v1" }
$API_KEY = $env:API_KEY

Write-Host "API Endpoint Testing" -ForegroundColor Cyan
Write-Host "====================" -ForegroundColor Cyan
Write-Host ""

Write-Host "1. Testing health endpoint..." -ForegroundColor Green
try {
    Invoke-RestMethod -Uri "$BASE_URL$API_PREFIX/health" -Method Get | ConvertTo-Json | Write-Host
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}
Write-Host ""

Write-Host "2. Testing API key requirement (should return 403)..." -ForegroundColor Green
try {
    Invoke-RestMethod -Uri "$BASE_URL$API_PREFIX/status/test-job-id" -Method Get -ErrorAction Stop | Out-Null
} catch {
    if ($_.Exception.Response.StatusCode -eq 403) {
        Write-Host "Correctly rejected request without API key" -ForegroundColor Green
    } else {
        Write-Host "Unexpected response: $($_.Exception.Response.StatusCode)" -ForegroundColor Yellow
    }
}
Write-Host ""

if ($API_KEY) {
    Write-Host "3. Testing status endpoint with API key (should return 404)..." -ForegroundColor Green
    try {
        $headers = @{ "X-API-Key" = $API_KEY }
        Invoke-RestMethod -Uri "$BASE_URL$API_PREFIX/status/nonexistent-job" `
            -Method Get `
            -Headers $headers `
            -ErrorAction Stop | Out-Null
    } catch {
        if ($_.Exception.Response.StatusCode -eq 404) {
            Write-Host "Correctly returned 404 (job not found)" -ForegroundColor Green
        } else {
            Write-Host "Unexpected response: $($_.Exception.Response.StatusCode)" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "3. Skipping authenticated status test because API_KEY is not set." -ForegroundColor Yellow
}
Write-Host ""

Write-Host "4. Swagger docs: $BASE_URL/docs" -ForegroundColor Cyan
Write-Host "5. ReDoc:       $BASE_URL/redoc" -ForegroundColor Cyan
Write-Host ""
Write-Host "====================" -ForegroundColor Cyan
Write-Host "Testing complete." -ForegroundColor Green
