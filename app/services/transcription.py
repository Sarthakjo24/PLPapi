from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_WORKER_SCRIPT = Path(__file__).resolve().parent.parent / "utils" / "whisper_worker.py"
_ALLOWED_LANGUAGES = {"en", "hi"}


class TranscriptionService:
    """Transcribe audio files using faster-whisper (subprocess) with OpenAI fallback."""

    def __init__(self, semaphore: asyncio.Semaphore | None = None) -> None:
        self._semaphore = semaphore or asyncio.Semaphore(
            settings.max_concurrent_transcriptions
        )
        self._openai: AsyncOpenAI | None = None
        if settings.openai_api_key and settings.openai_api_key != "sk-placeholder":
            self._openai = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
            )

    async def transcribe(self, audio_path: Path) -> dict:
        """Transcribe an audio file. Returns dict with transcript_text and metadata."""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        async with self._semaphore:
            if settings.use_faster_whisper:
                try:
                    payload = await asyncio.to_thread(
                        self._run_subprocess, audio_path
                    )
                    return self._postprocess(payload)
                except Exception as fw_err:
                    logger.warning(
                        "Faster-whisper failed for %s: %s — trying OpenAI fallback",
                        audio_path.name,
                        fw_err,
                    )
                    if self._openai is not None:
                        payload = await self._transcribe_openai(audio_path)
                        return self._postprocess(payload)
                    raise

            if self._openai is not None:
                payload = await self._transcribe_openai(audio_path)
                return self._postprocess(payload)

            raise RuntimeError("No transcription backend configured.")

    async def _transcribe_openai(self, audio_path: Path) -> dict:
        if self._openai is None:
            raise RuntimeError("OpenAI client not configured.")
        with audio_path.open("rb") as f:
            response = await self._openai.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=f,
                prompt=(
                    "Transcribe speech only if it is English or Hindi. "
                    "Return transcript in Roman script only (English/Hinglish). "
                    "If speech is in any other language, return empty transcript."
                ),
            )
        return {
            "transcript_text": (getattr(response, "text", "") or "").strip(),
            "detected_language": getattr(response, "language", None),
        }

    def _run_subprocess(self, audio_path: Path) -> dict:
        device = (
            "cpu" if sys.platform == "win32" else settings.faster_whisper_device
        )
        compute_type = (
            "float32"
            if sys.platform == "win32"
            else settings.faster_whisper_compute_type
        )

        env = os.environ.copy()
        env["OMP_NUM_THREADS"] = "1"
        env["OPENBLAS_NUM_THREADS"] = "1"
        env["MKL_NUM_THREADS"] = "1"
        env["NUMEXPR_NUM_THREADS"] = "1"

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(_WORKER_SCRIPT),
                    str(audio_path),
                    settings.faster_whisper_model,
                    device,
                    compute_type,
                ],
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Transcription timed out for {audio_path.name}"
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"Transcription subprocess exited {result.returncode}: "
                f"{result.stderr.strip()}"
            )

        stdout = result.stdout.strip()
        if not stdout:
            raise RuntimeError("Transcription subprocess produced no output.")
        return json.loads(stdout)

    def _postprocess(self, payload: dict) -> dict:
        text = self._normalize(payload.get("transcript_text"))
        lang = str(payload.get("detected_language") or "").strip().lower()

        if lang and lang not in _ALLOWED_LANGUAGES:
            payload["transcript_text"] = ""
            return payload
        if text and not self._is_latin(text):
            payload["transcript_text"] = ""
            return payload

        payload["transcript_text"] = text
        return payload

    @staticmethod
    def _normalize(text: object) -> str:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"[\u0000-\u001f\u007f]+", " ", cleaned).strip()
        return " ".join(cleaned.split())

    @staticmethod
    def _is_latin(text: str) -> bool:
        has_alpha = False
        for ch in text:
            if not ch.isalpha():
                continue
            has_alpha = True
            if "LATIN" not in unicodedata.name(ch, ""):
                return False
        return has_alpha
