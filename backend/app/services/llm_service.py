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

from app.core.config import redirect_loopback_to_host, running_in_container, settings
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
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code
        self.provider_code = provider_code
        self.retryable = retryable
        #: A plain-language explanation when the cause is recognisable. The raw
        #: provider message is often accurate but unhelpful.
        self.hint = hint


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
    #: The structured-output mode actually sent, which may differ from the one
    #: requested: `json_object` is upgraded to `json_schema` for runtimes that
    #: reject it, and either can be downgraded to `text` on refusal.
    effective_response_format: str = "text"
    format_downgraded: bool = False


def build_model_string(litellm_prefix: str, model_key: str) -> str:
    """``lm_studio`` + ``qwen2.5-7b-instruct`` -> ``lm_studio/qwen2.5-7b-instruct``."""
    prefix = (litellm_prefix or "").strip().strip("/")
    key = (model_key or "").strip()
    return f"{prefix}/{key}" if prefix else key


#: Runtimes whose OpenAI-compatible layer does not implement `json_object`.
#: LM Studio answers such a request with:
#:     'response_format.type' must be 'json_schema' or 'text'
#: This is a property of the runtime, not of a deployment, so it belongs in code
#: rather than in configuration.
_NO_JSON_OBJECT_PREFIXES: frozenset[str] = frozenset({"lm_studio"})


def resolve_response_format(
    mode: str, json_schema: dict | None, litellm_prefix: str
) -> tuple[dict | None, str]:
    """Pick the structured-output request the runtime will actually accept.

    Returns ``(payload, effective_mode)``.

    `json_object` is the OpenAI spelling and the natural default, but LM Studio
    rejects it outright. Since the exact output schema is already known, the
    request is *upgraded* to `json_schema` rather than downgraded to free text:
    strict structured output constrains the model to the contract instead of
    merely asking for valid JSON, which is strictly better for this task.
    """
    prefix = (litellm_prefix or "").strip().strip("/")

    if mode == "json_object" and prefix in _NO_JSON_OBJECT_PREFIXES:
        mode = "json_schema" if json_schema else "text"

    if mode == "json_object":
        return {"type": "json_object"}, mode

    if mode == "json_schema" and json_schema:
        return (
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "prosthetic_command",
                    "strict": True,
                    "schema": json_schema,
                },
            },
            mode,
        )

    return None, "text"


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
        # Two different retry knobs, and setting only one leaves the other at
        # its default.
        #
        # `num_retries` is LiteLLM's own loop. `max_retries` belongs to the
        # OpenAI client underneath it and defaults to 2. So a request with
        # num_retries=0 still ran three times, and a 120 s deadline produced a
        # failure at 242 s — the log said "did not answer within 120s after
        # 242.6s" and the arithmetic was the clue: 242.6 is two deadlines.
        #
        # Retrying a timeout is the worst case for it. The retry restarts prompt
        # processing from scratch, so it cannot succeed faster than the attempt
        # that just failed, and it doubles the wait before the researcher is
        # told anything.
        "max_retries": 0,
        **sampling,
    }

    if api_base:
        # A provider row seeded before the container knew better may still hold
        # a loopback address; correct it here so a stale row cannot break a run.
        kwargs["api_base"] = redirect_loopback_to_host(api_base)
    if api_key:
        kwargs["api_key"] = api_key
    elif is_local:
        # LM Studio / Ollama accept any non-empty key; LiteLLM requires one.
        kwargs["api_key"] = settings.lm_studio_api_key

    fmt, effective_format = resolve_response_format(
        response_format_mode, json_schema, litellm_prefix
    )
    if fmt is not None:
        kwargs["response_format"] = fmt

    requested = {k for k in _FRAGILE_PARAMS if k in sampling}
    format_downgraded = False
    started = time.perf_counter()

    async def _attempt() -> Any:
        return await acompletion(**kwargs)

    try:
        response = await _attempt()
    except Exception as exc:
        # One retry, and only for a refused structured-output request.
        #
        # Structured output is a capability declaration, and declarations are
        # sometimes wrong — a quantised build may not carry the grammar its
        # catalogue entry claims. Retrying as free text keeps the experiment
        # alive; the validator checks the JSON either way, and the downgrade is
        # recorded so the run is not silently different.
        #
        # Every other failure, and a failed retry, is wrapped below. Re-raising
        # raw here was a real defect: it bypassed the wrapping handlers entirely
        # and turned an ordinary provider rejection into an unhandled 500.
        retryable_format = fmt is not None and _is_format_rejection(exc)
        if retryable_format:
            kwargs.pop("response_format", None)
            try:
                response = await _attempt()
                effective_format = "text"
                format_downgraded = True
            except Exception as retry_exc:
                raise _wrap(retry_exc, model, is_local, sampling,
                            elapsed_s=time.perf_counter() - started,
                            timeout_s=kwargs["timeout"]) from retry_exc
        else:
            raise _wrap(exc, model, is_local, sampling,
                        elapsed_s=time.perf_counter() - started,
                        timeout_s=kwargs["timeout"]) from exc

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
        effective_response_format=effective_format,
        format_downgraded=format_downgraded,
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


def _wrap(
    exc: Exception,
    model: str,
    is_local: bool,
    sampling: dict[str, Any],
    elapsed_s: float | None = None,
    timeout_s: float | None = None,
) -> LlmCallError:
    """Normalise any provider failure into the platform's own error type.

    Everything that leaves this module must be an :class:`LlmCallError`, because
    that is what the orchestrator catches to record a `provider_error` execution.
    An escaping raw exception becomes an unhandled 500 and loses the run.

    ``elapsed_s`` is what distinguishes the two failures that look identical in
    the runtime's log. LM Studio prints "Client disconnected" whether we hit our
    own deadline or the connection died for some other reason, and without the
    elapsed time there is no way to tell which — so the obvious response is to
    raise the timeout, which fixes nothing if the cause was a dropped
    connection. Recording it turns a guess into a reading.
    """
    waited = "" if elapsed_s is None else f" after {elapsed_s:.1f}s"

    if isinstance(exc, asyncio.TimeoutError) or "timeout" in type(exc).__name__.lower():
        return LlmCallError(
            f"{type(exc).__name__}{waited}: {exc}",
            error_type="Timeout",
            retryable=True,
            hint=(
                f"The runtime did not answer within "
                f"{timeout_s or settings.llm_request_timeout_s:.0f}s{waited}. "
                "That deadline comes from LLM_REQUEST_TIMEOUT_S, which Compose "
                "reads from .env — so the value there overrides the application "
                "default, in both directions. "
                "On a local model this is usually prompt processing "
                "rather than a fault: a small model on CPU can spend minutes "
                "before emitting its first token. Check LM Studio's log for "
                "'Prompt processing progress' — if it is advancing, the model is "
                "working and the deadline is simply too short. Enabling GPU "
                "offload is the largest single improvement; shortening the EMG "
                "window is the next."
            ),
        )

    # A connection that dropped well inside the deadline is not a slow model.
    # Raising the timeout would be the natural reaction and the wrong one, so
    # the error says so explicitly.
    if (
        elapsed_s is not None
        and timeout_s
        and elapsed_s < timeout_s * 0.5
        and _is_connection_drop(exc)
    ):
        return LlmCallError(
            f"{type(exc).__name__}{waited}: {exc}",
            error_type="ConnectionLost",
            retryable=True,
            hint=(
                f"The connection to the runtime dropped{waited}, well inside the "
                f"{timeout_s:.0f}s deadline — so this is not a slow model and "
                "raising the timeout will not help. The usual causes are the "
                "backend restarting mid-request (uvicorn --reload picks up any "
                "edit to a mounted file and kills in-flight work), LM Studio "
                "unloading or swapping the model, or the machine sleeping."
            ),
        )

    return LlmCallError(
        f"{type(exc).__name__}{waited}: {exc}",
        error_type=type(exc).__name__,
        status_code=getattr(exc, "status_code", None),
        provider_code=str(getattr(exc, "code", "") or "") or None,
        retryable=_is_retryable(exc),
        hint=diagnose(exc, model=model, is_local=is_local, sampling=sampling),
    )


def _is_connection_drop(exc: Exception) -> bool:
    """Did the transport fail, as opposed to the provider rejecting the call?"""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return any(
        token in name or token in text
        for token in ("apiconnection", "connectionerror", "connectionreset",
                      "remoteprotocol", "incompleteread", "disconnect",
                      "connection closed", "server disconnected")
    )


def _is_format_rejection(exc: Exception) -> bool:
    """Did the runtime refuse the structured-output request specifically?"""
    text = str(exc).lower()
    return "response_format" in text or "json_schema" in text or "json_object" in text


def diagnose(
    exc: Exception,
    *,
    model: str,
    is_local: bool,
    sampling: dict[str, Any],
) -> str | None:
    """Translate a provider rejection into something the researcher can act on.

    A bare ``BadRequestError`` is accurate and useless. These are the causes
    that actually come up with local runtimes, and each one has a different fix.
    """
    text = str(exc).lower()

    if "context" in text and ("length" in text or "window" in text or "exceed" in text):
        return (
            "The prompt is longer than the context window the model was loaded "
            "with. The technical context block alone is around 3,500 tokens and "
            "the EMG matrix adds more. In LM Studio, raise the context length on "
            "the loaded model, or shorten the window (fewer EMG rows)."
        )

    if "response_format" in text or "json_object" in text or "json_schema" in text:
        return (
            "The runtime rejected the structured-output request. Set Response "
            "format to 'text' for this model, or load a build that supports "
            "JSON mode. The validator still checks the JSON either way."
        )

    if "does not exist" in text or "not found" in text or "no model" in text:
        return (
            f"The runtime does not recognise '{model.split('/', 1)[-1]}'. It may "
            "have been unloaded since it was imported — press 'Import loaded "
            "models' to refresh the catalogue."
        )

    if "grammar" in text or "unsupported" in text:
        dropped = [k for k in ("top_k", "seed", "frequency_penalty", "presence_penalty")
                   if k in sampling]
        if dropped:
            return (
                "The runtime rejected a sampling parameter. Try clearing "
                f"{', '.join(dropped)} for this model."
            )

    if is_local and ("connection" in text or "refused" in text):
        return (
            "The local runtime stopped responding mid-request. Check that the "
            "model is still loaded and that LM Studio's server is running."
        )

    return None


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

    base = redirect_loopback_to_host(api_base or settings.lm_studio_api_base).rstrip("/")
    url = f"{base}/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        hint = ""
        if running_in_container() and "host.docker.internal" not in base:
            hint = (
                " The backend is running in a container, so this address does "
                "not point at the host. Unset LM_STUDIO_API_BASE in .env and "
                "let the default apply."
            )
        elif "host.docker.internal" in base:
            hint = (
                " Check that LM Studio's server is started and that its OpenAI-"
                "compatible endpoint is on this port (Developer -> Start Server)."
            )
        return {
            "reachable": False,
            "api_base": base,
            "error": f"{type(exc).__name__}: {exc}.{hint}",
            "models": [],
        }

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
