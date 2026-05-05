from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── Request models ──


class QuestionPayload(BaseModel):
    """A single question with its recording URL and reference responses."""

    question_id: str
    question_text: str = Field(min_length=1)
    recording_url: str = Field(min_length=1)
    standard_responses: list[str] = Field(min_length=1)


class EvaluateRequest(BaseModel):
    """Full session evaluation request from WMS frontend."""

    session_id: str
    candidate_name: str
    candidate_id: str
    module_title: str = "Customer Handling Assessment"
    questions: list[QuestionPayload] = Field(min_length=1, max_length=10)
    scoring_weights: Optional[dict[str, float]] = None  # optional override


# ── Response models ──


class EvaluateResponse(BaseModel):
    """Immediate response after job submission."""

    job_id: Optional[str] = None
    status: str  # "received" | "rejected"
    message: str
    poll_url: Optional[str] = None


class QuestionResult(BaseModel):
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


class JobStatusResponse(BaseModel):
    """Polling response with progress or full results."""

    job_id: str
    status: str  # received | processing | completed | retrying | failed
    session_id: Optional[str] = None
    progress: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    message: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    overall_score: Optional[float] = None
    overall_summary: Optional[str] = None
    overall_strengths: Optional[list[str]] = None
    overall_weaknesses: Optional[list[str]] = None
    question_results: Optional[list[QuestionResult]] = None
    retry_count: Optional[int] = None
    error_detail: Optional[str] = None


class AckResponse(BaseModel):
    """Acknowledgement response."""

    message: str


# ── Rebuild models to resolve forward references for Pydantic v2 ──
QuestionPayload.model_rebuild()
EvaluateRequest.model_rebuild()
EvaluateResponse.model_rebuild()
QuestionResult.model_rebuild()
JobStatusResponse.model_rebuild()
AckResponse.model_rebuild()
