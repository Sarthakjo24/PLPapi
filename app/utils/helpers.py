from __future__ import annotations

import json
import re


def extract_json_object(text: str) -> dict:
    """Extract the first JSON object from a string, handling markdown fences."""
    cleaned = text.strip()

    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # Direct parse
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Find first balanced { ... } block
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No JSON object found in text.")

    depth = 0
    in_str = False
    escape = False

    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[start : i + 1])
                except json.JSONDecodeError:
                    raise ValueError("Found JSON block but it is not valid JSON.")

    raise ValueError("Incomplete JSON object in text.")


def normalize_transcript(text: str) -> str:
    """Normalize whitespace and control characters in transcript text."""
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"[\u0000-\u001f\u007f]+", " ", cleaned).strip()
    return " ".join(cleaned.split())


def coerce_numeric(value: object) -> float | None:
    """Safely coerce a value to float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", raw)
        return float(match.group(0)) if match else None


def coerce_list_points(value: object, limit: int = 3) -> list[str]:
    """Coerce a value into a list of string bullet points."""
    if isinstance(value, list):
        return [str(s).strip() for s in value if str(s).strip()][:limit]
    text = str(value or "").strip()
    if not text:
        return []
    parts = [
        re.sub(r"^[\-\*\d\.\)\s]+", "", seg).strip()
        for seg in re.split(r"[\n;]+", text)
        if seg.strip()
    ]
    cleaned = [p for p in parts if p]
    return cleaned[:limit] if cleaned else [text][:1]
