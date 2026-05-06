from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "plp:job"


def _job_key(job_id: str) -> str:
    return f"{_KEY_PREFIX}:{job_id}"


class JobManager:
    """Redis-backed job lifecycle manager for async evaluation jobs."""

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._redis = redis_client
        self._lock = asyncio.Lock()

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis

    async def _save_job(self, job_id: str, job_data: dict[str, Any]) -> None:
        redis_client = await self._get_redis()
        await redis_client.set(
            _job_key(job_id),
            json.dumps(job_data),
            ex=settings.redis_result_ttl_seconds,
        )

    async def create_job(
        self,
        job_id: str,
        session_id: str,
        question_count: int,
    ) -> dict[str, Any]:
        """Create a new job entry in Redis."""
        job_data: dict[str, Any] = {
            "job_id": job_id,
            "session_id": session_id,
            "status": "received",
            "question_count": question_count,
            "transcribed": 0,
            "evaluated": 0,
            "retry_count": 0,
            "progress": f"0/{question_count} evaluated",
            "message": (
                f"Job received. {question_count} questions queued for evaluation."
            ),
            "created_at": time.time(),
            "updated_at": time.time(),
            "results": None,
            "error_detail": None,
        }
        await self._save_job(job_id, job_data)
        return job_data

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve a job by ID."""
        redis_client = await self._get_redis()
        raw = await redis_client.get(_job_key(job_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def increment_progress(
        self,
        job_id: str,
        *,
        transcribed: int = 0,
        evaluated: int = 0,
    ) -> None:
        """Increment transcription and evaluation counters atomically."""
        async with self._lock:
            job = await self.get_job(job_id)
            if job is None:
                return

            total = int(job["question_count"])
            job["transcribed"] = min(total, int(job.get("transcribed", 0)) + transcribed)
            job["evaluated"] = min(total, int(job.get("evaluated", 0)) + evaluated)
            job["progress"] = f"{job['evaluated']}/{total} evaluated"
            job["status"] = "processing"
            job["updated_at"] = time.time()
            await self._save_job(job_id, job)

    async def update_status(
        self,
        job_id: str,
        status: str,
        message: str | None = None,
        error_detail: str | None = None,
        retry_count: int | None = None,
    ) -> None:
        """Update job status and optional fields."""
        async with self._lock:
            job = await self.get_job(job_id)
            if job is None:
                return
            job["status"] = status
            if message is not None:
                job["message"] = message
            if error_detail is not None:
                job["error_detail"] = error_detail
            if retry_count is not None:
                job["retry_count"] = retry_count
            job["updated_at"] = time.time()
            await self._save_job(job_id, job)

    async def store_results(self, job_id: str, results: dict[str, Any]) -> None:
        """Store completed evaluation results."""
        async with self._lock:
            job = await self.get_job(job_id)
            if job is None:
                return
            job["status"] = "completed"
            job["message"] = "Evaluation completed successfully."
            job["results"] = results
            job["error_detail"] = None
            job["updated_at"] = time.time()
            await self._save_job(job_id, job)

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job."""
        redis_client = await self._get_redis()
        return bool(await redis_client.delete(_job_key(job_id)))

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            redis_client = await self._get_redis()
            return bool(await redis_client.ping())
        except Exception:
            logger.exception("Redis health check failed.")
            return False

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is None:
            return

        close_method = getattr(self._redis, "aclose", None)
        if close_method is not None:
            await close_method()
        else:
            await self._redis.close()
        self._redis = None
