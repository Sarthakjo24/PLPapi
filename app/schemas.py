from __future__ import annotations

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class QuestionPayload(StrictModel):
    """A single question with its recording URL and reference responses."""

    question_id: str = Field(min_length=1, max_length=100)
    question_text: str = Field(min_length=1)
    recording_url: AnyHttpUrl
    standard_responses: list[str] = Field(min_length=1, max_length=10)

    @field_validator("standard_responses")
    @classmethod
    def ensure_standard_responses(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("standard_responses must include at least one value.")
        return cleaned


class EvaluateRequest(StrictModel):
    """Full session evaluation request from the WMS frontend."""

    session_id: str = Field(min_length=1, max_length=100)
    candidate_name: str = Field(min_length=1, max_length=200)
    candidate_id: str = Field(min_length=1, max_length=100)
    module_title: str = Field(default="Customer Handling Assessment", min_length=1)
    questions: list[QuestionPayload] = Field(min_length=1, max_length=10)
    scoring_weights: dict[str, float] | None = None

    @field_validator("scoring_weights")
    @classmethod
    def validate_scoring_weights(
        cls, value: dict[str, float] | None
    ) -> dict[str, float] | None:
        if value is None:
            return None

        allowed_keys = {
            "courtesy",
            "empathy",
            "respect",
            "tone",
            "communication",
        }
        invalid_keys = sorted(set(value) - allowed_keys)
        if invalid_keys:
            raise ValueError(
                "Unsupported scoring_weights keys: " + ", ".join(invalid_keys)
            )

        cleaned: dict[str, float] = {}
        for key, raw_value in value.items():
            numeric = float(raw_value)
            if numeric <= 0:
                raise ValueError(f"scoring_weights.{key} must be greater than 0.")
            cleaned[key] = numeric
        return cleaned


class EvaluateResponse(StrictModel):
    """Immediate response after job submission."""

    job_id: str
    status: Literal["received"]
    message: str
    poll_url: str


class QuestionResult(StrictModel):
    """Per-question evaluation result."""

    question_id: str
    transcript: str = ""
    total_score: float = 0.0
    courtesy_score: float = 0.0
    empathy_score: float = 0.0
    respect_score: float = 0.0
    tone_score: float = 0.0
    communication_score: float = 0.0
    strengths: list[str] = Field(default_factory=list)
    improvement_areas: list[str] = Field(default_factory=list)
    summary: str = ""


class JobStatusResponse(StrictModel):
    """Polling response with progress or full results."""

    job_id: str
    status: Literal[
        "received",
        "processing",
        "completed",
        "retrying",
        "failed",
        "unknown",
    ]
    session_id: str | None = None
    progress: str | None = None
    elapsed_seconds: float | None = None
    message: str | None = None
    processing_time_seconds: float | None = None
    overall_score: float | None = None
    overall_summary: str | None = None
    overall_strengths: list[str] | None = None
    overall_weaknesses: list[str] | None = None
    question_results: list[QuestionResult] | None = None
    retry_count: int | None = None
    error_detail: str | None = None


class AckResponse(StrictModel):
    """Acknowledgement response."""

    message: str


class HealthResponse(StrictModel):
    """Service health response."""

    status: Literal["ok"]
    service: str
    version: str
    environment: str
    dependencies: dict[str, str]
    docs: dict[str, str | None]
