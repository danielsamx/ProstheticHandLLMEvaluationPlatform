"""Contract tests for the current multimodal semantic prompt."""

from app.prompts.emg_context import EMG_CONTEXT_VERSION, build_emg_context
from app.prompts.system_prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION
from app.prompts.technical_context import TECHNICAL_CONTEXT_VERSION, build_technical_context


def test_prompt_versions_mark_the_semantic_redesign():
    assert SYSTEM_PROMPT_VERSION == "2.0"
    assert TECHNICAL_CONTEXT_VERSION == "2.0"
    assert EMG_CONTEXT_VERSION == "2.0"


def test_system_prompt_requires_tools_and_valid_control_meanings():
    assert "execute_handi_command exactly once" in SYSTEM_PROMPT
    assert "intent=no_action" in SYSTEM_PROMPT
    assert 'serial_command="S"' in SYSTEM_PROMPT
    assert "Never use hold" in SYSTEM_PROMPT


def test_semantic_policy_does_not_ask_the_model_to_process_signal_features():
    text = build_emg_context()
    assert "already been windowed, normalized, and serialized" in text
    assert "control_recommendation" in text
    assert "detected_pattern=co_contraction" in text
    assert "Encoder evidence can veto" in text
    for legacy_instruction in (
        "Evaluate jointly", "spatial distribution", "Flexor Digitorum",
        "Return STOP only when ALL",
    ):
        assert legacy_instruction not in text


def test_technical_context_contains_encoder_safety_policy():
    text = build_technical_context()
    assert "Physical encoders take priority over simulated encoders" in text
    assert "Stale telemetry" in text
    assert "no_action means no transmission" in text
    assert "STOP means intent=stop" in text


def test_prompt_contains_no_platform_or_transport_internals():
    frozen = SYSTEM_PROMPT + build_technical_context() + build_emg_context()
    for leak in ("Bluetooth", "PostgreSQL", "WebSocket", "frozen_context"):
        assert leak not in frozen
