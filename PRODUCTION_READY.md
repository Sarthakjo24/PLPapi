# Production Readiness Checklist

## 1. Security & Credentials ✓
- [ ] API_KEY in `.env` is NOT the default `"change-me-api-key"`
- [ ] OPENAI_API_KEY is valid and has proper permissions
- [ ] Redis credentials are secure (if using remote Redis)
- [ ] `.env` file is in `.gitignore` (never commit secrets)
- [ ] All sensitive data is environment variables
- [ ] CORS origins are set to real domain (not just localhost)

## 2. Dependencies & Versions ✓
- [ ] All packages from `requirements.txt` are installed
- [ ] Python version >= 3.10 (`python --version`)
- [ ] Redis is running and accessible
- [ ] OpenAI API is accessible

## 3. Configuration ✓
- [ ] Environment set to "prod" (not "dev")
- [ ] LOG_LEVEL appropriate for production (INFO or WARNING)
- [ ] WEB_WORKERS set properly (usually 4-8 for production)
- [ ] CORS_ORIGINS correct format: `["https://yourdomain.com"]`
- [ ] HOST is `0.0.0.0` or appropriate IP
- [ ] PORT is accessible (usually 8000)

## 4. Performance ✓
- [ ] API response time < 500ms for health checks
- [ ] Rate limiting configured appropriately
- [ ] Concurrency limits set per your resources:
  - MAX_CONCURRENT_TRANSCRIPTIONS
  - MAX_CONCURRENT_EVALUATIONS
- [ ] Timeout values appropriate for your use case

## 5. Logging & Monitoring ✓
- [ ] Structured logging enabled
- [ ] Log files being written to persistent storage
- [ ] Error handling covers all edge cases
- [ ] Monitoring/alerting setup (if applicable)

## 6. Database & Storage ✓
- [ ] Redis connection successful and stable
- [ ] Temp directory writable and has sufficient disk space
- [ ] Data retention (TTL) properly configured

## 7. Testing ✓
- [ ] Health endpoint responds: `GET /api/v1/health`
- [ ] Status endpoint requires API key: `GET /api/v1/status/{job_id}`
- [ ] Evaluate endpoint works: `POST /evaluate`
- [ ] Rate limiting works
- [ ] Error handling works (400, 401, 429, 500 responses)

## 8. Documentation ✓
- [ ] README.md is up to date
- [ ] API documentation accessible at `/docs`
- [ ] Integration guide for frontend provided

## 9. Deployment ✓
- [ ] Run on Linux in production (not Windows)
- [ ] Use Gunicorn (configured in `gunicorn.conf.py`)
- [ ] Use Nginx as reverse proxy (config in `deploy/nginx.conf`)
- [ ] Use systemd service (see `deploy/plp-api.service`)

## 10. Health & Monitoring ✓
- [ ] Implement `/health` checks in load balancer
- [ ] Setup log aggregation (ELK, Datadog, etc.)
- [ ] Monitor CPU, memory, disk usage
- [ ] Monitor Redis connection pool
- [ ] Alert on repeated errors

---

## How to Run Tests

```bash
# Run the production readiness test
python test_api.py

# OR test individual endpoints with curl
curl -X GET "http://localhost:8000/api/v1/health"
curl -X GET "http://localhost:8000/docs"  # Swagger UI
```

## Deployment Example (Linux)

```bash
# Production run with Gunicorn
python run.py  # Automatically detects Linux + ENV=prod

# OR manually:
gunicorn app.main:app -c gunicorn.conf.py --bind 0.0.0.0:8000 --workers 4
```

## Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| `JSONDecodeError` on CORS_ORIGINS | Ensure it's valid JSON: `["http://localhost:3000"]` |
| Redis connection refused | Check Redis is running: `redis-cli ping` |
| 403 Unauthorized | Include `X-API-Key` header with valid API_KEY |
| 429 Rate Limited | Wait or adjust `rate_limit_evaluate` / `rate_limit_status` |
| Timeout errors | Increase `OPENAI_TIMEOUT_SECONDS` or `request_timeout_seconds` |
