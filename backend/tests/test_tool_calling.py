import json
from types import SimpleNamespace

import pytest

from app.services.llm_service import LlmCallError, _compact_tool_schema, _tool_answer_of
from app.schemas.api import RunExecutionIn


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
