"""Environment-aware entry script.

Usage:
    python run.py
"""
from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "dev").strip().lower()
    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "8000")
    workers = os.getenv("WEB_WORKERS", "4")
    log_level = os.getenv("LOG_LEVEL", "info").strip().lower()

    is_windows = sys.platform == "win32"

    if env == "prod" and not is_windows:
        print(f"[PROD] Starting Gunicorn with {workers} workers on {host}:{port}")
        cmd = [
            sys.executable,
            "-m",
            "gunicorn",
            "app.main:app",
            "-c",
            "gunicorn.conf.py",
            "--bind",
            f"{host}:{port}",
            "--workers",
            workers,
            "--log-level",
            log_level,
        ]
        sys.exit(subprocess.call(cmd))

    reload_flag = env != "prod"
    print(f"[DEV] Starting Uvicorn on {host}:{port} (reload={reload_flag})")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        port,
        "--log-level",
        log_level,
    ]
    if reload_flag:
        cmd.append("--reload")
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
