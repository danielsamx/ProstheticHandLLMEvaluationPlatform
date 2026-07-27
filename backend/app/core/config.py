"""Application settings (pydantic-settings, 12-factor)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.hand_spec import LimitProfileId


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "Prosthetic Hand LLM Evaluation Platform"
    app_env: Literal["development", "staging", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    secret_key: str = "change-me"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:4200"])

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://phlab:phlab@localhost:5432/prosthetic_lab"
    database_url_sync: str = "postgresql+psycopg://phlab:phlab@localhost:5432/prosthetic_lab"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── LLM / LiteLLM ────────────────────────────────────────────────────────
    llm_request_timeout_s: float = 120.0
    llm_max_retries: int = 1
    litellm_proxy_base_url: str | None = None
    litellm_master_key: str | None = None
    litellm_verbose: bool = False
    #: Drop provider-unsupported sampling parameters instead of erroring.
    #: Essential for local runtimes (LM Studio, Ollama) that ignore top_k,
    #: presence_penalty, seed, etc. depending on the loaded model.
    litellm_drop_params: bool = True

    # ── LM Studio (primary local runtime) ────────────────────────────────────
    lm_studio_api_base: str = "http://localhost:1234/v1"
    lm_studio_api_key: str = "lm-studio"  # LM Studio ignores it but LiteLLM needs one
    ollama_api_base: str = "http://localhost:11434"

    # ── Experiment defaults ──────────────────────────────────────────────────
    default_limit_profile: LimitProfileId = LimitProfileId.TABLE_5_V3
    default_provider_slug: str = "lm_studio"
    #: Guard rail: an experiment batch may not exceed this many executions.
    max_batch_executions: int = 500

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json

                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
