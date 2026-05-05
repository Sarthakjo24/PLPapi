from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Environment ──
    environment: str = "dev"  # "dev" or "prod"

    # ── API Authentication ──
    api_key: str = "change-me-api-key"

    # ── OpenAI ──
    openai_api_key: str = "sk-placeholder"
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: int = 45

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"
    redis_result_ttl_seconds: int = 1800

    # ── Faster-Whisper ──
    use_faster_whisper: bool = True
    faster_whisper_model: str = "small"
    faster_whisper_device: str = "cpu"
    faster_whisper_compute_type: str = "int8"

    # ── Concurrency ──
    max_concurrent_transcriptions: int = 3
    max_concurrent_evaluations: int = 5
    max_retries: int = 3

    # ── Audio ──
    audio_download_timeout_seconds: int = 30
    max_audio_size_bytes: int = 50 * 1024 * 1024

    # ── Scoring weights (defaults) ──
    weight_courtesy: float = 1.5
    weight_empathy: float = 1.5
    weight_respect: float = 1.2
    weight_tone: float = 1.0
    weight_communication: float = 1.3

    # ── Server ──
    host: str = "0.0.0.0"
    port: int = 8000
    web_workers: int = 4
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    temp_audio_dir: str = "./tmp_audio"
    log_level: str = "INFO"
    prompt_template_path: str | None = None

    # ── Rate limiting ──
    rate_limit_evaluate: str = "10/minute"
    rate_limit_status: str = "60/minute"

    # ── Timeout ──
    request_timeout_seconds: int = 180

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors(cls, v: list[str] | str) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def is_prod(self) -> bool:
        return self.environment.strip().lower() == "prod"

    @property
    def scoring_weights(self) -> dict[str, float]:
        return {
            "courtesy": self.weight_courtesy,
            "empathy": self.weight_empathy,
            "respect": self.weight_respect,
            "tone": self.weight_tone,
            "communication": self.weight_communication,
        }

    @property
    def effective_temp_dir(self) -> Path:
        p = Path(self.temp_audio_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p.resolve()

    @property
    def effective_prompt_path(self) -> Path:
        if self.prompt_template_path:
            p = Path(self.prompt_template_path)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            return p.resolve()
        return PROJECT_ROOT / "prompt_template.txt"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
