"""The seven-stage safety gate. Nothing reaches the simulator without it."""

from __future__ import annotations

import json

import pytest

from app.domain.hand_spec import Handedness, LimitProfileId, get_limit_profile
from app.validation.pipeline import extract_json, validate_response
from app.validation.results import Severity, ValidationStage


def make_response(**overrides) -> str:
    payload = {
        "hand": "right",
        "intent": "gesture",
        "gesture": "C",
        "commands": [],
        "serial_command": "C",
        "detected_pattern": "power_grasp",
        "confidence": 0.9,
        "dominant_channels": ["CH1", "CH3"],
        "estimated_duration_ms": 900,
        "safety": {"within_limits": True, "emergency_stop": False, "collision_risk": False},
    }
    payload.update(overrides)
    return json.dumps(payload)


def positions_response(actuator: str, position: int, **overrides) -> str:
    overrides.setdefault("serial_command", f"{actuator}{position}")
    return make_response(
        intent="joint_positions",
        gesture=None,
        commands=[{"actuator": actuator, "position": position, "speed_pct": 60}],
        **overrides,
    )


# ── Happy path ──────────────────────────────────────────────────────────────


def test_valid_gesture_passes_every_stage():
    report = validate_response(make_response(), expected_hand=Handedness.RIGHT)
    assert report.passed
    assert report.stages_completed == [
        ValidationStage.PARSE, ValidationStage.SCHEMA, ValidationStage.PROTOCOL,
        ValidationStage.CONSISTENCY, ValidationStage.RANGE, ValidationStage.KINEMATIC,
        ValidationStage.SAFETY,
    ]
    assert report.resolved_pose is not None


def test_valid_joint_positions_pass():
    report = validate_response(positions_response("A", 320), expected_hand=Handedness.RIGHT)
    assert report.passed
    assert report.resolved_pose.actuator_positions["A"] == 320


def test_no_action_passes_without_a_pose():
    report = validate_response(
        make_response(intent="no_action", gesture=None, commands=[],
                      serial_command="NONE", detected_pattern="rest"),
        expected_hand=Handedness.RIGHT,
    )
    assert report.passed
    assert report.resolved_pose is None


# ── Stage 1: parse ──────────────────────────────────────────────────────────


def test_natural_language_is_rejected():
    report = validate_response(
        "I'll close the hand for you!", expected_hand=Handedness.RIGHT
    )
    assert not report.passed
    assert report.failed_stage is ValidationStage.PARSE


def test_empty_response_is_rejected():
    assert not validate_response("", expected_hand=Handedness.RIGHT).passed


def test_fenced_json_is_recovered_but_flagged():
    report = validate_response(
        f"```json\n{make_response()}\n```", expected_hand=Handedness.RIGHT
    )
    assert report.passed
    codes = {i.code for i in report.warnings}
    assert "JSON_REQUIRED_REPAIR" in codes


def test_extract_json_handles_prose_wrapper():
    payload, note = extract_json(f"Here you go: {make_response()} Hope that helps!")
    assert payload is not None
    assert note == "embedded_object"


# ── Stage 2: schema ─────────────────────────────────────────────────────────


def test_missing_required_field_is_rejected():
    payload = json.loads(make_response())
    del payload["confidence"]
    report = validate_response(json.dumps(payload), expected_hand=Handedness.RIGHT)
    assert not report.passed
    assert report.failed_stage is ValidationStage.SCHEMA


def test_extra_field_is_rejected():
    payload = json.loads(make_response())
    payload["explanation"] = "I decided to close the hand."
    report = validate_response(json.dumps(payload), expected_hand=Handedness.RIGHT)
    assert not report.passed
    assert report.failed_stage is ValidationStage.SCHEMA


def test_wrong_hand_is_rejected():
    report = validate_response(make_response(hand="left"), expected_hand=Handedness.RIGHT)
    assert not report.passed
    assert any(i.code == "HAND_MISMATCH" for i in report.errors)


def test_unknown_emg_channel_is_rejected():
    report = validate_response(
        make_response(dominant_channels=["CH9"]), expected_hand=Handedness.RIGHT
    )
    assert not report.passed


def test_gesture_and_commands_are_mutually_exclusive():
    report = validate_response(
        make_response(commands=[{"actuator": "A", "position": 10, "speed_pct": 60}]),
        expected_hand=Handedness.RIGHT,
    )
    assert not report.passed


# ── Stage 3/4: protocol & consistency ───────────────────────────────────────


def test_invented_command_letter_is_rejected():
    report = validate_response(
        positions_response("A", 320, serial_command="Z100"), expected_hand=Handedness.RIGHT
    )
    assert not report.passed
    assert report.failed_stage is ValidationStage.PROTOCOL


def test_serial_must_agree_with_the_commands_array():
    report = validate_response(
        positions_response("A", 320, serial_command="A200"), expected_hand=Handedness.RIGHT
    )
    assert not report.passed
    assert any(i.code == "COMMANDS_SERIAL_MISMATCH" for i in report.errors)


def test_gesture_letter_must_match_the_serial_line():
    report = validate_response(
        make_response(gesture="O", serial_command="C"), expected_hand=Handedness.RIGHT
    )
    assert not report.passed
    assert any(i.code == "GESTURE_SERIAL_MISMATCH" for i in report.errors)


# ── Stage 5: mechanical range ───────────────────────────────────────────────


def test_position_beyond_the_thumb_limit_is_rejected():
    report = validate_response(positions_response("E", 200), expected_hand=Handedness.RIGHT)
    assert not report.passed
    assert report.failed_stage is ValidationStage.RANGE
    assert any(i.code == "POSITION_OUT_OF_RANGE" for i in report.errors)


def test_the_same_command_can_pass_or_fail_depending_on_the_profile():
    """F380 is legal under Tabla 5 and illegal under the Anexo A envelope.

    This is exactly why the profile is versioned rather than hard-coded.
    """
    response = positions_response("F", 380)
    assert validate_response(
        response, expected_hand=Handedness.RIGHT,
        limit_profile=get_limit_profile(LimitProfileId.TABLE_5_V3),
    ).passed
    strict = validate_response(
        response, expected_hand=Handedness.RIGHT,
        limit_profile=get_limit_profile(LimitProfileId.ANNEX_A_V3),
    )
    assert not strict.passed
    assert strict.failed_stage is ValidationStage.RANGE


@pytest.mark.parametrize(
    "actuator,limit", [("A", 600), ("B", 550), ("C", 600), ("D", 550), ("E", 130), ("F", 400)]
)
def test_each_actuator_accepts_its_documented_maximum(actuator, limit):
    report = validate_response(
        positions_response(actuator, limit), expected_hand=Handedness.RIGHT
    )
    assert report.passed, [i.message for i in report.errors]


# ── Stage 7: safety ─────────────────────────────────────────────────────────


def test_collision_risk_is_warned_not_blocked():
    report = validate_response(make_response(), expected_hand=Handedness.RIGHT)
    assert report.passed
    assert any(i.severity is Severity.WARNING for i in report.issues)


def test_dishonest_self_assessment_is_recorded():
    report = validate_response(
        make_response(safety={"within_limits": False, "emergency_stop": False,
                              "collision_risk": False}),
        expected_hand=Handedness.RIGHT,
    )
    assert report.passed  # advisory only - the backend re-derives the truth
    assert any(i.code == "MODEL_SELF_REPORTED_UNSAFE" for i in report.warnings)


def test_emergency_stop_is_always_accepted():
    report = validate_response(
        make_response(intent="stop", gesture="S", serial_command="S",
                      detected_pattern="co_contraction", estimated_duration_ms=0),
        expected_hand=Handedness.RIGHT,
    )
    assert report.passed
    assert report.resolved_pose is None


def test_failed_validation_never_produces_a_pose():
    report = validate_response(positions_response("E", 999), expected_hand=Handedness.RIGHT)
    assert not report.passed
    assert report.resolved_pose is None
