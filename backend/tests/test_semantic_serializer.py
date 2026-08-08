from datetime import datetime, timedelta, timezone

from app.prompts.builder import build_prompt
from app.schemas.emg import EmgSourceMode, EmgWindow
from app.schemas.multimodal import EncoderTelemetry, MechanicalTelemetry
from app.services.semantic_serializer import serialize_multimodal_state


def _window(flexor: float, extensor: float, rows: int = 80) -> EmgWindow:
    samples = []
    for index in range(rows):
        sign = -1 if index % 2 else 1
        samples.append([sign * flexor] * 4 + [sign * extensor] * 3 + [0.0])
    return EmgWindow(samples=samples, source_mode=EmgSourceMode.DATASET, sample_rate_hz=200)


def test_semantic_serializer_detects_close_and_encoder_conflict():
    now = datetime.now(timezone.utc)
    telemetry = MechanicalTelemetry(actuators=[EncoderTelemetry(
        actuator="thumb", position=100, minimum=0, maximum=100,
        velocity=1, captured_at=now,
    )])
    state = serialize_multimodal_state(
        _window(0.9, 0.1), telemetry, mvc_by_channel=[1.0] * 8, now=now
    )
    assert state.emg.intent_candidate == "close"
    assert "thumb:close_at_closed_limit" in state.conflicts
    assert state.action_allowed is False


def test_stale_encoder_blocks_action():
    now = datetime.now(timezone.utc)
    telemetry = MechanicalTelemetry(actuators=[EncoderTelemetry(
        actuator="index", position=40, minimum=0, maximum=100,
        velocity=1, captured_at=now - timedelta(seconds=2),
    )])
    state = serialize_multimodal_state(
        _window(0.1, 0.9), telemetry, mvc_by_channel=[1.0] * 8, now=now
    )
    assert "index:stale_telemetry" in state.conflicts
    assert state.action_allowed is False


def test_co_contraction_recommends_valid_no_action_contract():
    state = serialize_multimodal_state(
        _window(0.9, 0.9), mvc_by_channel=[1.0] * 8
    )
    assert state.emg.intent_candidate == "uncertain"
    assert state.emg.detected_pattern_hint == "co_contraction"
    assert state.emg.control_recommendation == "no_action"
    assert state.action_allowed is False
    assert "hold" not in state.model_dump_json()


def test_prompt_contains_semantics_but_not_ground_truth():
    window = _window(0.9, 0.1)
    window.ground_truth_gesture = "secret-close-label"
    prompt = build_prompt(window, dynamic_content="semantic", mvc_by_channel=[1.0] * 8)
    assert "MULTIMODAL SEMANTIC STATE" in prompt.dynamic_prompt
    assert '"intent_candidate":"close"' in prompt.dynamic_prompt
    assert "secret-close-label" not in prompt.full_prompt
