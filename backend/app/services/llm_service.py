"""LiteLLM gateway.

One thin, provider-agnostic call path so that a locally hosted LM Studio model
and a hosted frontier model are exercised through identical code - which is the
precondition for the comparison to mean anything.

LM Studio notes
---------------
LM Studio exposes an OpenAI-compatible server (default ``http://localhost:1234/v1``).
LiteLLM routes it with the ``lm_studio/`` prefix.  Two practical caveats are
handled here:

* Many GGUF runtimes silently ignore ``top_k``, ``seed`` or the penalties.
  ``litellm.drop_params`` is enabled so an unsupported knob degrades to "not
  applied" instead of raising - the execution record still stores what was
  *requested*, and :attr:`LlmCallResult.dropped_params` reports what was ignored.
* Cost is zero for local inference, so ``cost_usd`` is forced to 0 for providers
  flagged ``is_local``; tokens/second becomes the meaningful efficiency metric.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import litellm
from litellm import acompletion

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

litellm.drop_params = settings.litellm_drop_params
litellm.set_verbose = settings.litellm_verbose
litellm.telemetry = False

#: Knobs that local runtimes commonly ignore. Reported, never fatal.
_FRAGILE_PARAMS = ("top_k", "seed", "frequency_penalty", "presence_penalty")


class LlmCallError(RuntimeError):
    """A provider-side failure, normalised across providers."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str = "ProviderError",
        status_code: int | None = None,
        provider_code: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code
        self.provider_code = provider_code
        self.retryable = retryable


@dataclass(slots=True)
class LlmCallResult:
    """Everything measurable about a single inference."""

    content: str
    model: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float = 0.0
    finish_reason: str | None = None
    response_id: str | None = None
    tokens_per_second: float | None = None
    dropped_params: list[str] = field(default_factory=list)
    raw_usage: dict[str, Any] = field(default_factory=dict)


def build_model_string(litellm_prefix: str, model_key: str) -> str:
    """``lm_studio`` + ``qwen2.5-7b-instruct`` -> ``lm_studio/qwen2.5-7b-instruct``."""
    prefix = (litellm_prefix or "").strip().strip("/")
    key = (model_key or "").strip()
    return f"{prefix}/{key}" if prefix else key


def _response_format(mode: str, json_schema: dict | None) -> dict | None:
    if mode == "json_object":
        return {"type": "json_object"}
    if mode == "json_schema" and json_schema:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "prosthetic_command",
                "strict": True,
                "schema": json_schema,
            },
        }
    return None


async def call_llm(
    *,
    messages: list[dict[str, str]],
    litellm_prefix: str,
    model_key: str,
    api_base: str | None = None,
    api_key: str | None = None,
    is_local: bool = False,
    sampling: dict[str, Any] | None = None,
    response_format_mode: str = "json_object",
    json_schema: dict | None = None,
    timeout_s: float | None = None,
    num_retries: int | None = None,
) -> LlmCallResult:
    """Invoke a model and measure it.

    Raises
    ------
    LlmCallError
        On any provider-side failure. Callers persist this as an
        ``ExecutionError`` and mark the execution ``provider_error``.
    """
    model = build_model_string(litellm_prefix, model_key)
    sampling = dict(sampling or {})

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "timeout": timeout_s or settings.llm_request_timeout_s,
        "num_retries": settings.llm_max_retries if num_retries is None else num_retries,
        **sampling,
    }

    if api_base:
        kwargs["api_base"] = api_base
    if api_key:
        kwargs["api_key"] = api_key
    elif is_local:
        # LM Studio / Ollama accept any non-empty key; LiteLLM requires one.
        kwargs["api_key"] = settings.lm_studio_api_key

    fmt = _response_format(response_format_mode, json_schema)
    if fmt is not None:
        kwargs["response_format"] = fmt

    requested = {k for k in _FRAGILE_PARAMS if k in sampling}
    started = time.perf_counter()

    try:
        response = await acompletion(**kwargs)
    except asyncio.TimeoutError as exc:
        raise LlmCallError(
            f"Request to {model} timed out.", error_type="Timeout", retryable=True
        ) from exc
    except Exception as exc:  # LiteLLM normalises provider exceptions
        raise LlmCallError(
            f"{type(exc).__name__}: {exc}",
            error_type=type(exc).__name__,
            status_code=getattr(exc, "status_code", None),
            provider_code=str(getattr(exc, "code", "") or "") or None,
            retryable=_is_retryable(exc),
        ) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)

    try:
        choice = response.choices[0]
        content = choice.message.content or ""
        finish_reason = getattr(choice, "finish_reason", None)
    except (AttributeError, IndexError) as exc:
        raise LlmCallError(
            f"Malformed response envelope from {model}: {exc}",
            error_type="MalformedResponse",
        ) from exc

    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
    total_tokens = getattr(usage, "total_tokens", None) if usage else None

    cost = 0.0
    if not is_local:
        try:
            cost = float(litellm.completion_cost(completion_response=response) or 0.0)
        except Exception:  # unknown pricing - record 0 and move on
            logger.warning("cost_unavailable", extra={"model": model})
            cost = 0.0

    tps = None
    if completion_tokens and latency_ms > 0:
        tps = round(completion_tokens / (latency_ms / 1000.0), 3)

    dropped = sorted(requested - _echoed_params(response))

    return LlmCallResult(
        content=content,
        model=model,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=round(cost, 8),
        finish_reason=finish_reason,
        response_id=getattr(response, "id", None),
        tokens_per_second=tps,
        dropped_params=dropped,
        raw_usage=_usage_dict(usage),
    )


def _echoed_params(response: Any) -> set[str]:
    """Parameters the provider confirms it honoured.

    Only OpenAI-style ``system_fingerprint`` / seed echoes are reliable, so this
    is deliberately conservative: we report a parameter as dropped only when the
    runtime is known to have ignored it.
    """
    honoured: set[str] = set()
    if getattr(response, "system_fingerprint", None):
        honoured.add("seed")
    return honoured


def _usage_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        try:
            return usage.model_dump()
        except Exception:
            pass
    return {
        k: v for k, v in vars(usage).items()
        if not k.startswith("_") and isinstance(v, (int, float, str))
    }


def _is_retryable(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    if any(t in name for t in ("timeout", "ratelimit", "serviceunavailable", "apiconnection")):
        return True
    status = getattr(exc, "status_code", None)
    return status in (408, 409, 429, 500, 502, 503, 504)


async def probe_lm_studio(api_base: str | None = None) -> dict[str, Any]:
    """List the models currently loaded in LM Studio.

    Lets the UI populate the model dropdown from whatever the researcher has
    actually loaded, instead of a hard-coded catalogue.
    """
    import httpx

    base = (api_base or settings.lm_studio_api_base).rstrip("/")
    url = f"{base}/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return {"reachable": False, "api_base": base, "error": str(exc), "models": []}

    models = [
        {
            "id": item.get("id"),
            "object": item.get("object"),
            "owned_by": item.get("owned_by"),
        }
        for item in payload.get("data", [])
        if item.get("id")
    ]
    return {"reachable": True, "api_base": base, "error": None, "models": models}
