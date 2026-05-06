from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "PLP Assessment API"
    api_description: str = (
        "AI-powered candidate assessment service for WMS integration."
    )
    api_version: str = "1.0.0"
    api_prefix: str = "/api/v1"

    # Environment
    environment: str = Field(
        default="dev",
        validation_alias=AliasChoices("ENVIRONMENT", "ENV"),
    )

    # API Authentication
    api_key: str = "change-me-api-key"

    # OpenAI
    openai_api_key: str = "sk-placeholder"
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: int = Field(default=45, gt=0)

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_result_ttl_seconds: int = Field(default=1800, gt=0)

    # Faster-Whisper
    use_faster_whisper: bool = True
    faster_whisper_model: str = "small"
    faster_whisper_device: str = "cpu"
    faster_whisper_compute_type: str = "int8"

    # Concurrency
    max_concurrent_transcriptions: int = Field(default=3, ge=1)
    max_concurrent_evaluations: int = Field(default=5, ge=1)
    max_retries: int = Field(default=3, ge=0)

    # Audio
    audio_download_timeout_seconds: int = Field(default=30, gt=0)
    max_audio_size_bytes: int = Field(default=50 * 1024 * 1024, gt=0)

    # Scoring weights
    weight_courtesy: float = Field(default=1.5, gt=0)
    weight_empathy: float = Field(default=1.5, gt=0)
    weight_respect: float = Field(default=1.2, gt=0)
    weight_tone: float = Field(default=1.0, gt=0)
    weight_communication: float = Field(default=1.3, gt=0)

    # Server
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    web_workers: int = Field(default=4, ge=1)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    temp_audio_dir: str = "./tmp_audio"
    log_level: str = "INFO"
    prompt_template_path: str | None = None
    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    openapi_url: str | None = "/openapi.json"

    # Rate limiting
    rate_limit_evaluate: str = "10/minute"
    rate_limit_status: str = "60/minute"

    # Timeout
    request_timeout_seconds: int = Field(default=180, gt=0)

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: Any) -> str:
        env = str(value or "dev").strip().lower()
        if env not in {"dev", "prod", "test"}:
            raise ValueError("environment must be one of: dev, prod, test")
        return env

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                parsed = json.loads(raw)
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ORIGINS JSON value must be a list.")
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in raw.split(",") if item.strip()]
        return [str(item).strip() for item in value if str(item).strip()]

    @field_validator("docs_url", "redoc_url", "openapi_url", mode="before")
    @classmethod
    def normalize_optional_url_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = str(value).strip()
        if not path or path.lower() in {"none", "null", "false", "off"}:
            return None
        return path if path.startswith("/") else f"/{path}"

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"

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
    def masked_redis_url(self) -> str:
        if "@" not in self.redis_url:
            return self.redis_url
        return self.redis_url.split("@", maxsplit=1)[-1]

    @property
    def effective_temp_dir(self) -> Path:
        path = Path(self.temp_audio_dir)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    @property
    def effective_prompt_path(self) -> Path:
        if self.prompt_template_path:
            path = Path(self.prompt_template_path)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            return path.resolve()
        return PROJECT_ROOT / "prompt_template.txt"

    def validate_runtime(self) -> None:
        errors: list[str] = []
        if self.is_prod and self.api_key == "change-me-api-key":
            errors.append("API_KEY must not use the default placeholder in production.")
        if self.is_prod and self.openai_api_key == "sk-placeholder":
            errors.append(
                "OPENAI_API_KEY must be configured with a real value in production."
            )
        if self.docs_url and self.docs_url == self.openapi_url:
            errors.append("DOCS_URL and OPENAPI_URL must not share the same path.")
        if self.redoc_url and self.redoc_url == self.openapi_url:
            errors.append("REDOC_URL and OPENAPI_URL must not share the same path.")
        if errors:
            raise RuntimeError("Invalid runtime configuration: " + " ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
