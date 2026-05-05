"""Gunicorn configuration for Linux production deployment.

Usage:
    gunicorn -c gunicorn.conf.py app.main:app
"""
import os

# ── Workers ──
# Rule of thumb: (2 × CPU cores) + 1
# Override via WEB_WORKERS env var
workers = int(os.getenv("WEB_WORKERS", "4"))
worker_class = "uvicorn.workers.UvicornWorker"

# ── Binding ──
bind = os.getenv("BIND", "127.0.0.1:8000")

# ── Timeouts ──
# Must be higher than your longest evaluation pipeline (~180s)
timeout = int(os.getenv("GUNICORN_TIMEOUT", "180"))
graceful_timeout = 30
keepalive = 5

# ── Logging ──
loglevel = os.getenv("LOG_LEVEL", "info").lower()
accesslog = "-"  # stdout
errorlog = "-"   # stderr

# ── Process naming ──
proc_name = "plp-assessment-api"

# ── Server mechanics ──
preload_app = False  # each worker loads its own app instance
max_requests = 500   # restart workers after N requests (prevents memory leaks)
max_requests_jitter = 50  # stagger restarts to avoid thundering herd
