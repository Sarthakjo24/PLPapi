"""Standalone subprocess script for faster-whisper transcription.

Usage:
    python whisper_worker.py <audio_path> <model_size> <device> <compute_type>

Outputs JSON to stdout:
    {"transcript_text": "...", "detected_language": "en", "processing_seconds": 3.5}
"""
from __future__ import annotations

import json
import sys
import time


def main() -> None:
    if len(sys.argv) < 5:
        print(
            json.dumps(
                {"error": "Usage: whisper_worker.py <audio_path> <model> <device> <compute_type>"}
            )
        )
        sys.exit(1)

    audio_path = sys.argv[1]
    model_size = sys.argv[2]
    device = sys.argv[3]
    compute_type = sys.argv[4]

    try:
        from faster_whisper import WhisperModel

        start = time.time()
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, info = model.transcribe(audio_path, beam_size=5)

        transcript_parts = []
        for segment in segments:
            transcript_parts.append(segment.text.strip())

        transcript_text = " ".join(transcript_parts).strip()
        elapsed = round(time.time() - start, 2)

        result = {
            "transcript_text": transcript_text,
            "detected_language": getattr(info, "language", None),
            "processing_seconds": elapsed,
        }
        print(json.dumps(result, ensure_ascii=False))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
