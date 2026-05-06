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

    def __init__(
        self,
        temp_dir: Path | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._temp_dir = temp_dir or settings.effective_temp_dir
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=settings.audio_download_timeout_seconds,
                follow_redirects=True,
            )
        return self._client

    async def download(self, url: str, session_id: str, question_id: str) -> Path:
        """Download audio from a public URL and save it to a temp file."""
        parsed_url = httpx.URL(str(url))
        if parsed_url.scheme not in {"http", "https"}:
            raise ValueError("recording_url must use http or https.")

        safe_session = self._sanitize(session_id)
        safe_question = self._sanitize(question_id)

        extension = Path(parsed_url.path or "").suffix or ".webm"
        dest_dir = self._temp_dir / safe_session
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{safe_question}{extension}"

        client = await self._get_client()
        bytes_written = 0

        try:
            async with client.stream("GET", str(parsed_url)) as response:
                response.raise_for_status()

                header_size = response.headers.get("content-length")
                if header_size and int(header_size) > settings.max_audio_size_bytes:
                    raise ValueError(
                        "Audio file exceeds size limit: "
                        f"{header_size} bytes (max {settings.max_audio_size_bytes})"
                    )

                with dest_file.open("wb") as file_handle:
                    async for chunk in response.aiter_bytes():
                        bytes_written += len(chunk)
                        if bytes_written > settings.max_audio_size_bytes:
                            raise ValueError(
                                "Audio file exceeds size limit while downloading: "
                                f"{bytes_written} bytes "
                                f"(max {settings.max_audio_size_bytes})"
                            )
                        file_handle.write(chunk)
        except Exception:
            dest_file.unlink(missing_ok=True)
            raise

        logger.info(
            "Downloaded audio session=%s question=%s size=%d path=%s",
            session_id,
            question_id,
            bytes_written,
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

    async def close(self) -> None:
        """Close the shared HTTP client if this instance created it."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _sanitize(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "unknown"
