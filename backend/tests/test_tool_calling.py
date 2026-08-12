import json
from types import SimpleNamespace

import pytest

from app.services.llm_service import (
    TOOL_INSTRUCTION,
    LlmCallError,
    _compact_tool_schema,
    _tool_answer_of,
    _with_tool_instruction,
)
from app.schemas.api import RunExecutionIn


def test_the_tool_instruction_survives_a_multimodal_user_turn():
    """The regression that took down every tool-calling run.

    The branch was written when the user turn was always a string, and it went
    on concatenating one onto it after the image flow made the turn a list of
    typed parts: `TypeError: can only concatenate list (not "str") to list`,
    raised inside the request, after the picture had been rendered.

    The instruction must arrive as its own part *after* the image, so the last
    thing the model reads is still how it has to answer — and the image must
    still be there, which is the half the exception hid.
    """
    messages = [
        {"role": "system", "content": "frozen blocks"},
        {"role": "user", "content": [
            {"type": "text", "text": "DERIVED FEATURES"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ]},
    ]

    shaped = _with_tool_instruction(messages)
    parts = shaped[-1]["content"]

    assert [part["type"] for part in parts] == ["text", "image_url", "text"]
    assert parts[-1]["text"] == TOOL_INSTRUCTION
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")

    # The originals are untouched: the frozen prompt is what the record stores,
    # and an invocation detail must not edit it in place.
    assert messages[-1]["content"] == [
        {"type": "text", "text": "DERIVED FEATURES"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
    ]


def test_a_text_only_turn_still_gets_the_instruction_appended():
    shaped = _with_tool_instruction([{"role": "user", "content": "table"}])
    assert shaped[0]["content"] == "table" + TOOL_INSTRUCTION


def test_execution_request_schema_resolves_tool_calling_literal():
    RunExecutionIn.model_rebuild(force=True)
    schema = RunExecutionIn.model_json_schema()
    assert schema["properties"]["invocation_mode"]["enum"] == ["structured_output", "tool_calling"]


def test_extracts_native_handi_tool_call_arguments():
    arguments = {"intent": "gesture", "gesture": "O", "commands": [], "serial_command": "O", "confidence": 0.9}
    message = SimpleNamespace(tool_calls=[SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="execute_handi_command", arguments=json.dumps(arguments)),
    )])
    name, call_id, parsed = _tool_answer_of(message)
    assert name == "execute_handi_command"
    assert call_id == "call-1"
    assert parsed == arguments


def test_rejects_malformed_tool_arguments():
    message = SimpleNamespace(tool_calls=[SimpleNamespace(
        id="call-2", function=SimpleNamespace(name="execute_handi_command", arguments="{bad"),
    )])
    with pytest.raises(LlmCallError, match="not valid JSON"):
        _tool_answer_of(message)


def test_does_not_accept_a_different_tool_as_handi_command():
    message = SimpleNamespace(tool_calls=[SimpleNamespace(
        id="call-3", function=SimpleNamespace(name="untrusted_tool", arguments="{}"),
    )])
    assert _tool_answer_of(message) == ("untrusted_tool", "call-3", None)


def test_lm_studio_uses_string_tool_choice():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "app" / "services" / "llm_service.py").read_text()
    assert 'kwargs["tool_choice"] = "required"' in source
    assert 'kwargs["tool_choice"] = {"type"' not in source


def test_tool_schema_drops_prose_but_keeps_constraints():
    schema = {"title": "Command", "description": "long prose", "properties": {
        "confidence": {"title": "Confidence", "type": "number", "minimum": 0, "maximum": 1}
    }, "required": ["confidence"]}
    compact = _compact_tool_schema(schema)
    assert "title" not in compact and "description" not in compact
    assert compact["properties"]["confidence"] == {"type": "number", "minimum": 0, "maximum": 1}
    assert compact["required"] == ["confidence"]


def test_tool_mode_explicitly_disallows_json_in_assistant_content():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "app" / "services" / "llm_service.py").read_text()
    assert "You must respond by calling execute_handi_command exactly once" in source
    assert "Do not emit" in source
