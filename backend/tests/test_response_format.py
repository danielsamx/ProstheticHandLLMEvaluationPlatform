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


def _load_resolver():
    """Extract the resolver without importing litellm."""
    source = (BACKEND / "app" / "services" / "llm_service.py").read_text()
    tree = ast.parse(source)
    wanted = {"resolve_response_format", "_NO_JSON_OBJECT_PREFIXES", "_is_format_rejection"}
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


def test_the_execution_path_requests_plain_text():
    """The reply is a command line, not a document.

    There is no schema to enforce and no JSON mode to ask for, so the
    capability negotiation that used to sit here has nothing left to decide.
    `resolve_response_format` is retained because the LiteLLM layer is generic
    and a future caller may want structured output again.
    """
    source = (BACKEND / "app" / "services" / "execution_service.py").read_text()
    assert 'response_format_mode="text"' in source
    assert "json_schema=None" in source
    assert "llm_json_schema" not in source


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
