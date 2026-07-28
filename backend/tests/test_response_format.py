"""Structured-output negotiation.

`json_object` is the OpenAI spelling and the natural default, but LM Studio
answers it with:

    'response_format.type' must be 'json_schema' or 'text'

That is a property of the runtime, not of a deployment, so the mapping lives in
code. The request is *upgraded* to `json_schema` rather than downgraded to free
text: the exact output schema is already known, and strict structured output
constrains the model to the contract instead of merely asking for valid JSON.
"""

from __future__ import annotations

import ast
import pathlib
import types

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _load_resolver(extra: set[str] | None = None):
    """Extract pure helpers from the module without importing litellm.

    litellm is a heavy optional dependency and these functions do not touch it.
    Loading them by AST keeps the logic they encode — which is where the real
    bugs have been — testable in any environment.
    """
    source = (BACKEND / "app" / "services" / "llm_service.py").read_text()
    tree = ast.parse(source)
    wanted = {"resolve_response_format", "_NO_JSON_OBJECT_PREFIXES", "_is_format_rejection"}
    wanted |= extra or set()
    body = [
        node for node in tree.body
        if (isinstance(node, (ast.FunctionDef,)) and node.name in wanted)
        or (isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") in wanted)
    ]
    module = types.ModuleType("resolver")
    module.__dict__["frozenset"] = frozenset
    exec(compile(ast.Module(body=body, type_ignores=[]), "<resolver>", "exec"), module.__dict__)
    return module


SCHEMA = {"type": "object", "properties": {"hand": {"type": "string"}}}


def test_lm_studio_gets_json_schema_not_json_object():
    """The exact rejection this guards against, reproduced as a rule."""
    resolver = _load_resolver()
    payload, mode = resolver.resolve_response_format("json_object", SCHEMA, "lm_studio")

    assert mode == "json_schema"
    assert payload["type"] == "json_schema"
    assert payload["json_schema"]["schema"] == SCHEMA
    assert payload["json_schema"]["strict"] is True


def test_openai_still_gets_json_object():
    """The upgrade is runtime-specific; it must not leak to providers that
    implement `json_object` correctly."""
    resolver = _load_resolver()
    payload, mode = resolver.resolve_response_format("json_object", SCHEMA, "openai")

    assert mode == "json_object"
    assert payload == {"type": "json_object"}


def test_lm_studio_without_a_schema_falls_back_to_text():
    """Sending `json_object` anyway would be rejected; text at least runs."""
    resolver = _load_resolver()
    payload, mode = resolver.resolve_response_format("json_object", None, "lm_studio")

    assert mode == "text"
    assert payload is None


@pytest.mark.parametrize("prefix", ["lm_studio", "openai", "anthropic", ""])
def test_text_is_never_rewritten(prefix):
    resolver = _load_resolver()
    payload, mode = resolver.resolve_response_format("text", SCHEMA, prefix)
    assert (payload, mode) == (None, "text")


@pytest.mark.parametrize("prefix", ["lm_studio", "openai"])
def test_explicit_json_schema_is_honoured_everywhere(prefix):
    resolver = _load_resolver()
    payload, mode = resolver.resolve_response_format("json_schema", SCHEMA, prefix)
    assert mode == "json_schema"
    assert payload["type"] == "json_schema"


def test_prefix_is_tolerant_of_slashes():
    resolver = _load_resolver()
    _, mode = resolver.resolve_response_format("json_object", SCHEMA, "/lm_studio/")
    assert mode == "json_schema"


# ── Refusal detection ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "message",
    [
        "'response_format.type' must be 'json_schema' or 'text'",
        "json_schema is not supported by this model",
        "response_format json_object unsupported",
    ],
)
def test_format_rejections_are_recognised(message):
    resolver = _load_resolver()
    assert resolver._is_format_rejection(Exception(message))


@pytest.mark.parametrize(
    "message",
    [
        "the number of tokens exceeds the context length",
        "connection refused",
        "model does not exist",
    ],
)
def test_other_failures_are_not_mistaken_for_format_rejections(message):
    """A context-length failure must not trigger a silent downgrade to text —
    the retry would fail the same way and the run would be misreported."""
    resolver = _load_resolver()
    assert not resolver._is_format_rejection(Exception(message))


# ── The effective format is recorded ────────────────────────────────────────


def test_the_format_actually_used_is_persisted():
    """Two runs are only comparable if the runtime accepted the same mode."""
    source = (BACKEND / "app" / "services" / "execution_service.py").read_text()
    assert "execution.response_format = call.effective_response_format" in source


def test_a_downgrade_is_recorded_as_a_warning():
    source = (BACKEND / "app" / "services" / "execution_service.py").read_text()
    assert "format_downgraded" in source
    assert "not constrained by the schema" in source


# ── The run path asks for no structured output ──────────────────────────────


def test_the_execution_path_asks_for_constrained_decoding():
    """The reply is a JSON object, so the schema is sent as `response_format`.

    Constraining the decoder removes the largest single failure mode — prose
    wrapped around the JSON — at the runtime, rather than catching it afterwards
    in the parse stage where it has already cost a wasted execution.
    """
    source = (BACKEND / "app" / "services" / "execution_service.py").read_text()
    assert "response_format_mode=config.response_format" in source
    assert "json_schema=response_json_schema()" in source


# ── Retry policy ────────────────────────────────────────────────────────────


def test_the_provider_layer_does_not_retry():
    """LiteLLM's retry restarts the request including prompt processing.

    For a timeout that guarantees a second failure and doubles the wall time:
    a 120 s timeout became 242 s of waiting. The only retry worth making is the
    structured-output downgrade, which changes the request and is performed
    explicitly in `call_llm`.
    """
    from app.core.config import Settings

    assert Settings(_env_file=None).llm_max_retries == 0


def test_the_timeout_suits_local_inference():
    """A small model on CPU can spend a minute on prompt processing alone."""
    from app.core.config import Settings

    assert Settings(_env_file=None).llm_request_timeout_s >= 300


# ── Failure attribution ─────────────────────────────────────────────────────


def test_a_dropped_connection_is_recognised_as_transport_not_provider():
    """LM Studio logs "Client disconnected" whether we hit our own deadline or
    the connection died for another reason, so its log cannot tell them apart.

    Elapsed time can. A connection that died at 15s inside a 1800s deadline is
    not a slow model, and saying so matters: the natural reaction to "client
    disconnected" is to raise the timeout, which fixes nothing when the cause
    was the backend restarting mid-request.
    """
    resolver = _load_resolver(extra={"_is_connection_drop"})
    drop = resolver._is_connection_drop

    class APIConnectionError(Exception):
        pass

    assert drop(APIConnectionError("server disconnected"))
    assert drop(ConnectionResetError("reset by peer"))
    assert not drop(ValueError("'response_format.type' must be 'json_schema'"))


def test_the_wrapper_records_how_long_it_waited():
    """Whatever the cause, the first question is "how long did it wait?" — and
    the answer has to be in the stored error, not only in a log line."""
    source = (BACKEND / "app" / "services" / "llm_service.py").read_text()
    assert "elapsed_s=time.perf_counter() - started" in source
    assert 'waited = "" if elapsed_s is None else f" after {elapsed_s:.1f}s"' in source
    assert 'error_type="ConnectionLost"' in source
