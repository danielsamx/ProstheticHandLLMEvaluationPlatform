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


# ── The tool instruction and the multimodal turn ────────────────────────────


def _tool_shaper():
    return _load_resolver({"_with_tool_instruction", "TOOL_INSTRUCTION"})


def test_the_tool_instruction_survives_a_multimodal_user_turn():
    """The regression that took down every tool-calling run.

    The branch was written when the user turn was always a string, and it went
    on concatenating one onto it after the image flow made the turn a list of
    typed parts:

        TypeError: can only concatenate list (not "str") to list

    raised inside the request, after the picture had been rendered. The
    instruction must arrive as its own part *after* the image, so the last thing
    the model reads is still how it has to answer — and the image must still be
    there, which is the half the exception hid.
    """
    module = _tool_shaper()
    messages = [
        {"role": "system", "content": "frozen blocks"},
        {"role": "user", "content": [
            {"type": "text", "text": "DERIVED FEATURES"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ]},
    ]

    parts = module._with_tool_instruction(messages)[-1]["content"]

    assert [part["type"] for part in parts] == ["text", "image_url", "text"]
    assert parts[-1]["text"] == module.TOOL_INSTRUCTION
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")

    # The originals are untouched: the frozen prompt is what the record stores,
    # and an invocation detail must not edit it in place.
    assert len(messages[-1]["content"]) == 2


def test_a_text_only_turn_still_gets_the_instruction_appended():
    module = _tool_shaper()
    shaped = module._with_tool_instruction([{"role": "user", "content": "table"}])
    assert shaped[0]["content"] == "table" + module.TOOL_INSTRUCTION


# ── What the model is allowed to answer ─────────────────────────────────────


def test_the_offered_schema_permits_only_open_close_and_no_action():
    """The schema is enforced, so it is the strongest statement of the contract.

    It used to offer fourteen gesture letters, six actuators and an integer
    position each, while the technical block said the only permitted answers
    were O, C and no_action. The model was handed two contracts and the wider
    one was the one the runtime enforced.
    """
    from app.schemas.llm_output import response_json_schema

    schema = response_json_schema()
    properties = schema["properties"]

    assert properties["intent"]["enum"] == ["gesture", "no_action"]
    assert properties["gesture"]["anyOf"][0]["enum"] == ["O", "C"]
    for absent in ("commands", "safety", "hand"):
        assert absent not in properties
    assert "$defs" not in schema


def test_the_offered_schema_carries_no_prose():
    """Pydantic copies a class docstring into `description`, and it would travel
    to the model on every request. The tool path strips descriptions; the
    `response_format` path does not, so the schema has to be clean at source."""
    import json

    from app.schemas.llm_output import response_json_schema

    assert "description" not in json.dumps(response_json_schema())


def test_the_full_contract_still_renders_for_the_stored_records():
    """Executions run under the fourteen-gesture contract are still in the
    database, and reading one back must not depend on a schema that only exists
    in git history."""
    from app.schemas.llm_output import full_response_json_schema

    assert "$defs" in full_response_json_schema()


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


def test_both_retry_knobs_are_pinned_to_zero():
    """A timeout that fires at twice its own deadline is a retry nobody asked for.

    `num_retries` is LiteLLM's loop; `max_retries` belongs to the OpenAI client
    underneath and defaults to 2. Setting only the first left the second at its
    default, so a 120 s deadline produced a failure at 242.6 s — and the error
    message read "did not answer within 120s after 242.6s", which is the sort of
    contradiction that sends someone looking in the wrong place.

    Retrying a timeout is its worst case: the retry restarts prompt processing
    from scratch, so it cannot succeed faster than the attempt that just failed,
    and it doubles the wait before anyone is told anything.
    """
    source = (BACKEND / "app" / "services" / "llm_service.py").read_text()
    assert '"max_retries": 0,' in source
    assert '"num_retries": settings.llm_max_retries' in source


def test_the_shipped_timeout_is_a_ceiling_not_a_hosted_api_figure():
    """The value in .env wins over the application default, in both directions.

    Compose reads .env for `${VAR}` interpolation *and* passes it into the
    container, so a stale 120 there silently beat the 1800 in config.py. The
    example file is what a fresh install copies, so it is the one that has to be
    right.
    """
    import re

    for name in (".env.example", ".env"):
        path = BACKEND.parent / name
        if not path.exists():
            continue
        match = re.search(r"^LLM_REQUEST_TIMEOUT_S=(\d+)", path.read_text(), re.M)
        assert match, f"{name} does not set LLM_REQUEST_TIMEOUT_S"
        assert int(match.group(1)) >= 900, (
            f"{name} sets a {match.group(1)}s deadline; local CPU inference "
            "regularly needs longer than that for prompt processing alone."
        )


# ── Reasoning models ────────────────────────────────────────────────────────


def _load_answer_reader():
    return _load_resolver(extra={"_answer_of", "_ANSWER_FIELDS"})


class _Message:
    def __init__(self, **fields):
        for key, value in fields.items():
            setattr(self, key, value)

    def __getattr__(self, _name):  # anything not set is absent
        return None


def test_an_answer_stranded_on_the_reasoning_channel_is_recovered():
    """The failure this guards, verbatim from a Qwen3.5-9B run:

        "content": "",
        "reasoning_content": "{ \\"intent\\": \\"no_action\\", ... }"

    with finish_reason "stop" and 26 reasoning tokens. Reasoning models split
    their output in two, and this one put the entire answer on the thinking
    channel. Reading only `content` recorded it as an empty response and a parse
    failure, while the model had in fact answered.
    """
    reader = _load_answer_reader()
    text, channel = reader._answer_of(
        _Message(content="", reasoning_content='{"intent": "no_action"}')
    )
    assert text == '{"intent": "no_action"}'
    assert channel == "reasoning_content"


def test_content_wins_whenever_it_has_anything_in_it():
    """The fallback must never override a real answer. A reasoning model that
    fills both channels puts its working-out in the reasoning field, and taking
    that over the answer would be strictly worse than the original bug."""
    reader = _load_answer_reader()
    text, channel = reader._answer_of(
        _Message(content='{"the": "answer"}', reasoning_content="let me think...")
    )
    assert text == '{"the": "answer"}'
    assert channel == "content"


def test_a_genuinely_empty_reply_stays_empty():
    """Recovery must not manufacture an answer where there was none: an empty
    response is a real result and has to keep failing the parse stage."""
    reader = _load_answer_reader()
    assert reader._answer_of(_Message(content="")) == ("", "content")
    assert reader._answer_of(_Message(content="   ", reasoning_content="  ")) == (
        "", "content",
    )


def test_the_recovery_channel_is_recorded_rather_than_hidden():
    """A model that only ever answers on its thinking channel behaves
    differently from one that answers where asked, and the record has to be able
    to tell them apart."""
    source = (BACKEND / "app" / "services" / "llm_service.py").read_text()
    assert "content_channel: str = \"content\"" in source
    assert "content_channel=content_channel," in source

    orchestrator = (BACKEND / "app" / "services" / "execution_service.py").read_text()
    assert 'if call.content_channel != "content":' in orchestrator
