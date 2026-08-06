"""Application settings (pydantic-settings, 12-factor)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.hand_spec import LimitProfileId


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "Prosthetic Hand LLM Evaluation Platform"
    #: Stamped on every execution so a result can be tied to the code that
    #: produced it, independently of the prompt hashes.
    app_version: str = "1.1.0"
    app_env: Literal["development", "staging", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 480
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:4200",
            "http://127.0.0.1:4200",
        ]
    )
    #: In development the UI is reached by whatever hostname is convenient -
    #: localhost, 127.0.0.1, or the LAN address the dev server prints for
    #: testing on a tablet. A browser treats each as a distinct origin, so an
    #: exact-match list turns a harmless URL choice into nine failed requests
    #: with no usable error. Locked to loopback and private ranges; production
    #: still uses the explicit list only.
    cors_allow_local_origins: bool = True

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://phlab:phlab@localhost:5432/prosthetic_lab"
    database_url_sync: str = "postgresql+psycopg://phlab:phlab@localhost:5432/prosthetic_lab"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── LLM / LiteLLM ────────────────────────────────────────────────────────
    #: Local CPU inference is slow in a way hosted APIs are not: a 3B model can
    #: spend minutes on prompt processing alone before emitting a token. 120 s
    #: was a hosted-API figure applied to a workstation.
    #:
    #: 1800 s is not an expectation that a run takes half an hour — it is a
    #: deliberately useless ceiling. The timeout's only remaining job is to stop
    #: a truly wedged request from holding a connection forever; it is no longer
    #: a judgement about how long inference "should" take, because on a cold
    #: model on CPU that figure is unknowable in advance and guessing it wrong
    #: destroys the run at the last moment.
    #:
    #: Override with LLM_REQUEST_TIMEOUT_S in the environment.
    llm_request_timeout_s: float = 1800.0
    #: Zero on purpose.
    #:
    #: LiteLLM's retry restarts the request from scratch, including prompt
    #: processing. For a timeout that guarantees a second failure and doubles
    #: the wall time — 120 s became 242 s of waiting for nothing. The only retry
    #: worth making here is the structured-output downgrade, which `call_llm`
    #: performs itself because it changes the request.
    llm_max_retries: int = 0
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

    @property
    def cors_origin_regex(self) -> str | None:
        """Loopback and private-network origins on any port, for development."""
        if not self.cors_allow_local_origins or self.app_env == "production":
            return None
        return (
            r"^https?://("
            r"localhost|127\.0\.0\.1|\[::1\]|"
            r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
            r"192\.168\.\d{1,3}\.\d{1,3}|"
            r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
            r")(:\d+)?$"
        )

    @model_validator(mode="after")
    def _reach_local_runtimes_from_a_container(self) -> "Settings":
        """Point local runtimes at the Docker host when running in a container."""
        self.lm_studio_api_base = redirect_loopback_to_host(self.lm_studio_api_base)
        self.ollama_api_base = redirect_loopback_to_host(self.ollama_api_base)
        return self

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


#: Hostnames that mean "this machine" — and therefore mean the *container*
#: once the backend is running inside one.
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

#: How a container reaches a service on the Docker host. Docker Desktop provides
#: it automatically; docker-compose.yml adds the host-gateway mapping so the
#: same name works on native Linux.
_DOCKER_HOST_ALIAS = "host.docker.internal"


def running_in_container() -> bool:
    """True when this process is inside a container.

    ``/.dockerenv`` is created by the Docker runtime; the cgroup check covers
    Podman and older runtimes that do not write it.
    """
    if Path("/.dockerenv").exists():
        return True
    try:
        return "docker" in Path("/proc/1/cgroup").read_text() or "containerd" in Path(
            "/proc/1/cgroup"
        ).read_text()
    except OSError:
        return False


def redirect_loopback_to_host(url: str) -> str:
    """Rewrite a loopback URL so a containerised process reaches the host.

    Inside a container ``localhost`` is the container itself, so a local model
    runtime on the developer's machine is unreachable at that address. This is
    easy to get wrong from configuration alone: Compose interpolates ``.env``
    when resolving ``${VAR:-default}``, so a ``localhost`` value in ``.env``
    silently overrides the correct default in ``docker-compose.yml``. Correcting
    it here means the backend works regardless of which of those files is wrong.
    """
    if not url or not running_in_container():
        return url
    parts = urlsplit(url)
    if parts.hostname not in _LOOPBACK_HOSTS:
        return url
    netloc = _DOCKER_HOST_ALIAS + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
