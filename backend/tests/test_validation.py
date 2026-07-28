"""The five-stage safety gate.

The model emits one line: the serial command. Nothing reaches the simulator, and
later the prosthesis, without clearing every stage.

Two stages that existed for the JSON contract are gone. `schema` checked an
object against a declared shape and `consistency` checked that object against
the command line beside it — with one representation instead of two there is
nothing left to disagree.
"""

from __future__ import annotations

import pytest

from app.domain.hand_spec import Handedness, LimitProfileId, get_limit_profile
from app.validation.pipeline import extract_command, validate_response
from app.validation.results import Severity, ValidationStage


def check(response: str, *, hand: Handedness = Handedness.RIGHT, profile=None):
    return validate_response(response, expected_hand=hand, limit_profile=profile)


# ── Happy path ──────────────────────────────────────────────────────────────


def test_a_bare_gesture_passes_every_stage():
    report = check("C")
    assert report.passed
    assert report.stages_completed == [
        ValidationStage.PARSE,
        ValidationStage.PROTOCOL,
        ValidationStage.RANGE,
        ValidationStage.KINEMATIC,
        ValidationStage.SAFETY,
    ]
    assert report.normalised_serial == "C"
    assert report.resolved_pose is not None


def test_positions_pass_and_resolve_to_a_pose():
    report = check("A320,B180")
    assert report.passed
    assert report.resolved_pose.actuator_positions["A"] == 320
    assert report.resolved_pose.actuator_positions["B"] == 180


def test_the_rest_command_passes():
    """`O` is how the model declines to act, so it must always be executable."""
    report = check("O")
    assert report.passed
    assert report.parsed_command.gesture == "O"


def test_emergency_stop_passes_and_produces_no_pose():
    report = check("S")
    assert report.passed
    assert report.resolved_pose is None


def test_whitespace_around_the_command_is_tolerated():
    assert check("  A320  ").passed


# ── Stage 1: parse ──────────────────────────────────────────────────────────


def test_prose_with_no_command_is_rejected():
    report = check("I would close the hand for you.")
    assert not report.passed
    assert report.failed_stage is ValidationStage.PARSE


def test_an_empty_response_is_rejected():
    assert not check("").passed
    assert not check("   \n  ").passed


def test_a_json_reply_is_recovered_but_never_counts_as_clean():
    """A model still emitting the old shape is not silently rewarded.

    The command is recovered from the quoted value, because refusing outright
    would throw away a run whose intent is unambiguous. But the repair is
    recorded, so the response fails the `is_bare_json` measure that tracks
    instruction adherence — which is the number that should notice.
    """
    report = check('{"serial_command": "C", "intent": "gesture"}')
    assert report.passed
    assert report.normalised_serial == "C"
    assert any(i.code == "COMMAND_REQUIRED_REPAIR" for i in report.warnings)


def test_prose_containing_a_quoted_non_command_is_not_mistaken_for_one():
    report = check('I recommend "Co-contraction" therefore stopping')
    assert not report.passed
    assert report.failed_stage is ValidationStage.PARSE


@pytest.mark.parametrize(
    "response,expected",
    [
        ("```\nC\n```", "fenced_code_block"),
        ('The command is "C".', "quoted_string"),
        ("Based on the EMG:\nC\nThis closes the hand.", "embedded_in_prose"),
    ],
)
def test_a_wrapped_command_is_recovered_but_flagged(response, expected):
    """Recovery exists so the metrics can distinguish *how* a model deviates,
    not to be lenient: the run stops counting as clean."""
    report = check(response)
    assert report.passed
    assert any(i.code == "COMMAND_REQUIRED_REPAIR" for i in report.warnings)
    assert extract_command(response)[1] == expected


def test_a_bare_command_needs_no_repair():
    report = check("A320")
    assert not any(i.code == "COMMAND_REQUIRED_REPAIR" for i in report.issues)


# ── Stage 2: protocol ───────────────────────────────────────────────────────


def test_an_invented_command_letter_is_rejected():
    report = check("Z100")
    assert not report.passed
    assert report.failed_stage is ValidationStage.PROTOCOL


def test_lowercase_is_rejected():
    report = check("a320")
    assert not report.passed


def test_a_gesture_cannot_be_mixed_with_positions():
    report = check("P,A320")
    assert not report.passed
    assert report.failed_stage is ValidationStage.PROTOCOL


def test_an_actuator_cannot_be_addressed_twice():
    report = check("A320,A100")
    assert not report.passed


def test_bare_c_closes_the_hand_and_c400_moves_the_middle_finger():
    """The documented ambiguity, end to end."""
    closed = check("C")
    assert closed.parsed_command.gesture == "C"
    assert closed.parsed_command.intent == "gesture"

    middle = check("C400")
    assert middle.parsed_command.gesture is None
    assert middle.parsed_command.commands[0]["actuator"] == "C"


# ── Stage 3: range ──────────────────────────────────────────────────────────


def test_a_position_beyond_the_thumb_limit_is_rejected():
    report = check("E200")
    assert not report.passed
    assert report.failed_stage is ValidationStage.RANGE
    assert any(i.code == "POSITION_OUT_OF_RANGE" for i in report.errors)


@pytest.mark.parametrize(
    "command", ["A600", "B550", "C600", "D550", "E130", "F400"]
)
def test_each_actuator_accepts_its_documented_maximum(command):
    report = check(command)
    assert report.passed, [i.message for i in report.errors]


def test_the_same_command_passes_or_fails_by_profile():
    """F380 is legal under Tabla 5 and illegal under the Anexo A envelope, which
    is why the profile is versioned rather than hard-coded."""
    assert check("F380", profile=get_limit_profile(LimitProfileId.TABLE_5_V3)).passed

    strict = check("F380", profile=get_limit_profile(LimitProfileId.ANNEX_A_V3))
    assert not strict.passed
    assert strict.failed_stage is ValidationStage.RANGE


# ── Stage 5: safety ─────────────────────────────────────────────────────────


def test_an_exclusive_command_cannot_be_combined():
    report = check("S,A320")
    assert not report.passed


def test_collision_risk_is_warned_not_blocked():
    """Severity depends on whether an object is in the grasp, so the useful
    thing is to make the frequency measurable rather than to refuse."""
    report = check("C")
    assert report.passed
    assert any(i.severity is Severity.WARNING for i in report.issues)


def test_a_failed_response_never_produces_a_pose():
    report = check("E999")
    assert not report.passed
    assert report.resolved_pose is None


# ── Derived description ─────────────────────────────────────────────────────


def test_the_pattern_label_describes_the_command_not_the_model_s_opinion():
    """It is used to group results, so it has to be a property of what was sent
    rather than something the model asserted about its own reasoning."""
    assert check("C").parsed_command.detected_pattern == "close"
    assert check("O").parsed_command.detected_pattern == "open"
    assert check("A320").parsed_command.detected_pattern == "custom_pose"


def test_the_hand_is_taken_from_the_experiment_not_the_response():
    """The model no longer states which hand, so it cannot get it wrong."""
    assert check("C", hand=Handedness.LEFT).parsed_command.hand == "left"
