from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from statistics import mean
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from app.config import settings
from app.utils.helpers import coerce_list_points, coerce_numeric, extract_json_object

logger = logging.getLogger(__name__)

_RETRYABLE = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    APIError,
    TimeoutError,
    ConnectionError,
    OSError,
    RuntimeError,
    ValueError,
)


class EvaluationService:
    """OpenAI-powered evaluation of candidate responses."""

    def __init__(self, semaphore: asyncio.Semaphore | None = None) -> None:
        self._semaphore = semaphore or asyncio.Semaphore(
            settings.max_concurrent_evaluations
        )
        self._client: AsyncOpenAI | None = None
        if settings.openai_api_key and settings.openai_api_key != "sk-placeholder":
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
            )
        self._prompt_template: str | None = None

    @property
    def prompt_template(self) -> str:
        if self._prompt_template is None:
            path = settings.effective_prompt_path
            if path.exists():
                self._prompt_template = path.read_text(encoding="utf-8")
            else:
                self._prompt_template = self._default_prompt_template()
        return self._prompt_template

    async def evaluate_answer(
        self,
        question_text: str,
        transcript_text: str,
        standard_responses: list[str],
        module_title: str,
        scoring_weights: dict[str, float],
    ) -> dict[str, Any]:
        """Evaluate a single candidate answer against standard responses."""
        if not transcript_text.strip():
            return {
                "total_score": 0.0,
                "sentiment_breakdown": {
                    "courtesy": 0.0,
                    "empathy": 0.0,
                    "respect": 0.0,
                    "tone": 0.0,
                },
                "handling_breakdown": {
                    "communication_clarity": 0.0,
                    "engagement": 0.0,
                    "problem_handling_approach": 0.0,
                },
                "strengths": ["No supported speech was detected in the recording."],
                "improvement_areas": [
                    "Provide a clear spoken response in supported English or Hindi."
                ],
                "final_summary": (
                    "The recording could not be evaluated because no supported "
                    "transcript was produced."
                ),
            }

        if self._client is None:
            raise RuntimeError("OpenAI client not configured (missing OPENAI_API_KEY).")

        prompt = self._build_prompt(
            question_text=question_text,
            transcript_text=transcript_text,
            standard_responses=standard_responses,
            module_title=module_title,
            scoring_weights=scoring_weights,
        )

        last_error: Exception | None = None
        for attempt in range(settings.max_retries):
            try:
                async with self._semaphore:
                    return await self._invoke(prompt)
            except _RETRYABLE as exc:
                last_error = exc
                if attempt < settings.max_retries - 1:
                    wait = float(2**attempt)
                    logger.warning(
                        "Evaluation attempt %d failed: %s; retrying in %.0fs",
                        attempt + 1,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)

        raise RuntimeError(
            f"Evaluation failed after {settings.max_retries} attempts: {last_error}"
        )

    async def summarize_session(
        self,
        module_title: str,
        candidate_name: str,
        candidate_id: str,
        evaluated_answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate an overall performance summary across all evaluated answers."""
        if not evaluated_answers:
            return {}
        if self._client is None:
            return self._heuristic_summary(evaluated_answers)

        prompt = self._build_summary_prompt(
            module_title=module_title,
            candidate_name=candidate_name,
            candidate_id=candidate_id,
            evaluated_answers=evaluated_answers,
        )

        last_error: Exception | None = None
        for attempt in range(settings.max_retries):
            try:
                async with self._semaphore:
                    result = await self._invoke(
                        prompt,
                        system_msg=(
                            "You create fair, balanced, and accurate candidate "
                            "performance summaries. Be encouraging where warranted. "
                            "Return JSON only."
                        ),
                    )
                    if result.get("overall_summary"):
                        return result
                    raise ValueError("Missing overall_summary in model output.")
            except _RETRYABLE as exc:
                last_error = exc
                if attempt < settings.max_retries - 1:
                    await asyncio.sleep(float(2**attempt))

        logger.warning(
            "OpenAI summary failed after retries (%s), using heuristic fallback.",
            last_error,
        )
        return self._heuristic_summary(evaluated_answers)

    async def _invoke(
        self,
        prompt: str,
        system_msg: str | None = None,
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("OpenAI client not configured.")

        default_system = (
            "You are a fair and balanced behavior-based customer service evaluator. "
            "Be encouraging where warranted and constructive in feedback. "
            "Return JSON only."
        )
        response = await self._client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": system_msg or default_system},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        payload = extract_json_object(content)
        return self._normalize_payload(payload)

    def _build_prompt(
        self,
        question_text: str,
        transcript_text: str,
        standard_responses: list[str],
        module_title: str,
        scoring_weights: dict[str, float],
    ) -> str:
        base = (
            self.prompt_template
            .replace("{{MODULE_TITLE}}", module_title)
            .replace("{{QUESTION_TITLE}}", question_text[:120])
            .replace("{{QUESTION_TRANSCRIPT}}", question_text)
            .replace("{{QUESTION_TEXT}}", question_text)
            .replace("{{CANDIDATE_TRANSCRIPT}}", transcript_text)
            .replace("{{CANDIDATE_RESPONSE}}", transcript_text)
            .replace(
                "{{STANDARD_RESPONSES_LIST}}",
                json.dumps(standard_responses, ensure_ascii=False, indent=2),
            )
            .replace(
                "{{SCORING_WEIGHTS_JSON}}",
                json.dumps(scoring_weights, ensure_ascii=False, indent=2),
            )
        )
        suffix = (
            "\n\nOutput guidance:\n"
            "- If reference standard responses are unavailable, use the scenario "
            "transcript and behavior rubric only.\n"
            "- Provide at least one item in both `strengths` and `improvement_areas`.\n"
            "- Keep feedback constructive and specific to the candidate's actual transcript.\n"
        )
        return f"{base}{suffix}"

    def _build_summary_prompt(
        self,
        module_title: str,
        candidate_name: str,
        candidate_id: str,
        evaluated_answers: list[dict[str, Any]],
    ) -> str:
        return (
            "You are evaluating overall behavior-based customer support performance.\n\n"
            f"MODULE TITLE:\n{module_title}\n\n"
            f"CANDIDATE NAME:\n{candidate_name}\n\n"
            f"CANDIDATE ID:\n{candidate_id}\n\n"
            "EVALUATED RESPONSES JSON:\n"
            f"{json.dumps(evaluated_answers, ensure_ascii=False, indent=2)}\n\n"
            "Instructions:\n"
            "- `total_score`: overall 0-10 score.\n"
            "- `strengths`: 2-4 key recurring strengths.\n"
            "- `weaknesses`: 1-3 constructive areas for improvement.\n"
            "- `question_wise_scores`: array with `question_id`, `score` per question.\n"
            "- `overall_summary`: 90-150 word performance narrative.\n\n"
            "Return strict JSON:\n"
            '{"total_score":0,"strengths":[""],"weaknesses":[""],'
            '"question_wise_scores":[{"question_id":"","score":0}],'
            '"overall_summary":""}\n'
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if normalized.get("total_score") is None and normalized.get("score") is not None:
            normalized["total_score"] = normalized["score"]
        normalized["total_score"] = coerce_numeric(normalized.get("total_score"))

        sentiment = normalized.get("sentiment_breakdown") or {}
        for key in ("courtesy", "respect", "empathy", "tone"):
            if sentiment.get(key) is None and normalized.get(f"{key}_score") is not None:
                sentiment[key] = normalized[f"{key}_score"]
            sentiment[key] = coerce_numeric(sentiment.get(key))
        normalized["sentiment_breakdown"] = sentiment

        handling = normalized.get("handling_breakdown") or {}
        communication_score = normalized.get("communication_score")
        for key in (
            "communication_clarity",
            "engagement",
            "problem_handling_approach",
        ):
            if handling.get(key) is None and communication_score is not None:
                handling[key] = communication_score
            handling[key] = coerce_numeric(handling.get(key))
        normalized["handling_breakdown"] = handling

        normalized["strengths"] = coerce_list_points(normalized.get("strengths"))
        if normalized.get("improvement_areas") is None:
            normalized["improvement_areas"] = normalized.get("weakness")
        normalized["improvement_areas"] = coerce_list_points(
            normalized.get("improvement_areas")
        )

        if not str(normalized.get("final_summary") or "").strip():
            normalized["final_summary"] = str(normalized.get("feedback") or "").strip()

        return normalized

    def _heuristic_summary(
        self, evaluated_answers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        scores = []
        question_scores = []
        all_strengths: list[str] = []
        all_weaknesses: list[str] = []
        seen_strengths: set[str] = set()
        seen_weaknesses: set[str] = set()

        for answer in evaluated_answers:
            score = answer.get("total_score")
            try:
                numeric_score = float(score)
            except (TypeError, ValueError):
                continue
            scores.append(numeric_score)
            question_scores.append(
                {
                    "question_id": answer.get("question_id", ""),
                    "score": round(numeric_score, 2),
                }
            )
            for item in answer.get("strengths", []):
                normalized_item = str(item).strip().lower()
                if (
                    normalized_item
                    and normalized_item not in seen_strengths
                    and len(all_strengths) < 4
                ):
                    seen_strengths.add(normalized_item)
                    all_strengths.append(str(item).strip())
            for item in answer.get("improvement_areas", []):
                normalized_item = str(item).strip().lower()
                if (
                    normalized_item
                    and normalized_item not in seen_weaknesses
                    and len(all_weaknesses) < 3
                ):
                    seen_weaknesses.add(normalized_item)
                    all_weaknesses.append(str(item).strip())

        average_score = round(mean(scores), 2) if scores else None
        count = len(evaluated_answers)
        summary = (
            f"Across {count} responses"
            + (f" with an average score of {average_score}/10" if average_score else "")
            + f", strengths include {', '.join(all_strengths) or 'polite tone'}."
            + " Areas for improvement: "
            + f"{', '.join(all_weaknesses) or 'showing more empathy'}."
        )
        return {
            "total_score": average_score,
            "strengths": all_strengths,
            "weaknesses": all_weaknesses,
            "question_wise_scores": question_scores,
            "overall_summary": summary,
        }

    async def close(self) -> None:
        """Close the OpenAI client if present."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    @staticmethod
    def _default_prompt_template() -> str:
        return (
            "MODULE: {{MODULE_TITLE}}\n\n"
            "SCENARIO / QUESTION:\n{{QUESTION_TEXT}}\n\n"
            "CANDIDATE'S RESPONSE (transcript):\n{{CANDIDATE_TRANSCRIPT}}\n\n"
            "STANDARD REFERENCE RESPONSES:\n{{STANDARD_RESPONSES_LIST}}\n\n"
            "SCORING WEIGHTS:\n{{SCORING_WEIGHTS_JSON}}\n\n"
            "Evaluate the candidate's response on these dimensions (each 0-10):\n"
            "courtesy, empathy, respect, tone, communication_clarity.\n\n"
            "Return JSON:\n"
            '{"total_score":0,"sentiment_breakdown":{"courtesy":0,"empathy":0,'
            '"respect":0,"tone":0},"handling_breakdown":{"communication_clarity":0,'
            '"engagement":0,"problem_handling_approach":0},'
            '"strengths":[""],"improvement_areas":[""],"final_summary":""}\n'
        )
