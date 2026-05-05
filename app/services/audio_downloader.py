from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AudioDownloader:
    """Download audio files from public URLs to a temp directory."""

    def __init__(self, temp_dir: Path | None = None) -> None:
        self._temp_dir = temp_dir or settings.effective_temp_dir

    async def download(self, url: str, session_id: str, question_id: str) -> Path:
        """Download audio from a public URL and save to a temp file."""
        safe_session = self._sanitize(session_id)
        safe_question = self._sanitize(question_id)

        # Determine extension from URL
        url_path = url.split("?")[0]
        extension = Path(url_path).suffix or ".webm"

        dest_dir = self._temp_dir / safe_session
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{safe_question}{extension}"

        async with httpx.AsyncClient(
            timeout=settings.audio_download_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            content_length = len(response.content)
            if content_length > settings.max_audio_size_bytes:
                raise ValueError(
                    f"Audio file exceeds size limit: {content_length} bytes "
                    f"(max {settings.max_audio_size_bytes})"
                )

            dest_file.write_bytes(response.content)

        logger.info(
            "Downloaded audio session=%s question=%s size=%d path=%s",
            session_id,
            question_id,
            content_length,
            dest_file,
        )
        return dest_file

    def cleanup_session(self, session_id: str) -> None:
        """Remove all temp audio files for a session."""
        safe_session = self._sanitize(session_id)
        session_dir = self._temp_dir / safe_session
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
            logger.info("Cleaned up temp audio for session=%s", session_id)

    @staticmethod
    def _sanitize(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "unknown"
