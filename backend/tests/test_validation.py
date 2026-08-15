"""The seven-stage safety gate.

The model emits a JSON object. Nothing reaches the simulator, and later the
prosthesis, without clearing every stage.

Two stages exist only because the response states its decision twice: `schema`
checks the object has the declared shape, and `consistency` checks the
`serial_command` agrees with the `intent`/`gesture`/`commands` beside it. Those
disagreements are the point of the structured contract — with a bare command
line there is nothing that *can* disagree, so a model contradicting itself would
be invisible.
"""

from __future__ import annotations

import json

import pytest

from app.domain.hand_spec import Handedness, LimitProfileId, get_limit_profile
from app.validation.pipeline import extract_json, validate_response
from app.validation.results import Severity, ValidationStage

ALL_STAGES = [
    ValidationStage.PARSE,
    ValidationStage.SCHEMA,
    ValidationStage.PROTOCOL,
    ValidationStage.CONSISTENCY,
    ValidationStage.RANGE,
    ValidationStage.KINEMATIC,
    ValidationStage.SAFETY,
]


def response(
    serial: str,
    *,
    intent: str | None = None,
    gesture: str | None = "__auto__",
    commands: list[dict] | None = None,
    hand: str = "right",
    confidence: float = 0.8,
    within_limits: bool = True,
    **extra,
) -> str:
    """Build a well-formed response for `serial`, so tests can break one thing.

    Defaults are inferred from the command itself, which means a test that wants
    an inconsistency has to state it explicitly. Written the other way round —
    every field spelled out in every test — a typo would read as a deliberate
    inconsistency and the suite would be testing its own fixtures.
    """
    tokens = [t.strip() for t in serial.split(",") if t.strip()]
    positions = [t for t in tokens if len(t) > 1]
    is_gesture = bool(tokens) and not positions

    if intent is None:
        intent = "stop" if serial == "S" else "gesture" if is_gesture else "joint_positions"
    if gesture == "__auto__":
        gesture = tokens[0] if is_gesture else None
    if commands is None:
        commands = [
            {"actuator": t[0], "position": int(t[1:]), "speed_pct": 60}
            for t in positions
        ]

    payload = {
        "hand": hand,
        "intent": intent,
        "gesture": gesture,
        "commands": commands,
        "serial_command": serial,
        "confidence": confidence,
        "safety": {"within_limits": within_limits},
    }
    payload.update(extra)
    return json.dumps(payload)


def check(raw: str, *, hand: Handedness = Handedness.RIGHT, profile=None):
    return validate_response(raw, expected_hand=hand, limit_profile=profile)


# ── The current contract: one field ─────────────────────────────────────────


def test_a_bare_gesture_reply_passes_every_stage():
    """`{"gesture": "C"}` is the whole contract now.

    The pipeline below it is unchanged — protocol, range, kinematics, safety all
    run exactly as before — because the reply is expanded into the wide shape
    before stage 2. What no longer exists is the possibility of a reply that
    disagrees with itself.
    """
    report = check('{"gesture": "C"}')
    assert report.passed, [i.message for i in report.errors]
    assert report.stages_completed == ALL_STAGES
    assert report.normalised_serial == "C"
    assert report.resolved_pose is not None

    # Derived, not claimed: the model said one letter.
    assert report.parsed_command.intent == "gesture"
    assert report.parsed_command.serial_command == "C"
    assert report.parsed_command.confidence is None


def test_an_empty_gesture_is_a_refusal_and_transmits_nothing():
    report = check('{"gesture": ""}')
    assert report.passed, [i.message for i in report.errors]
    assert report.parsed_command.is_inaction
    assert report.normalised_serial is None
    assert report.resolved_pose is None
    assert report.stages_completed == ALL_STAGES


@pytest.mark.parametrize("payload", [
    '{"gesture": "P"}',            # a real firmware gesture, not permitted here
    '{"gesture": "o"}',            # lower case
    '{"gesture": "O", "confidence": 0.9}',   # a field the contract does not have
    '{"gesture": null}',
])
def test_anything_but_the_three_values_is_a_schema_violation(payload):
    """Not repaired, not coerced.

    `P` is the sharpest case: it is a gesture the firmware really implements, so
    every stage below would accept it and the hand would perform a pinch. The
    contract says three answers, and the schema is where that is enforced.
    """
    report = check(payload)
    assert not report.passed
    assert report.failed_stage is ValidationStage.SCHEMA
    assert report.normalised_serial is None


# ── The older contract, for the records written under it ────────────────────


def test_a_gesture_passes_every_stage():
    report = check(response("C"))
    assert report.passed, [i.message for i in report.errors]
    assert report.stages_completed == ALL_STAGES
    assert report.normalised_serial == "C"
    assert report.resolved_pose is not None


def test_positions_pass_and_resolve_to_a_pose():
    report = check(response("A320,B180"))
    assert report.passed, [i.message for i in report.errors]
    assert report.resolved_pose.actuator_positions["A"] == 320
    assert report.resolved_pose.actuator_positions["B"] == 180


def test_a_refusal_passes_and_transmits_nothing():
    """`no_action` means no command at all, and that is a complete answer.

    It used to require a command, which forced a contradiction: the model had to
    name a movement it had just declined to make. It had nothing to name, so it
    reached for the nearest thing — one run invented the string "no_action", the
    next sent `S`. Both failed validation, and both were the schema's fault.

    `O` was the only accepted spelling, and it is the wrong one: on a hand that
    is holding something, opening it drops the object. The protocol has no "hold
    position" command, so the honest representation of inaction is the absence
    of a command rather than the presence of a harmless-looking one.
    """
    report = check(json.dumps({"intent": "no_action", "confidence": 0.2}))
    assert report.passed, [i.message for i in report.errors]
    assert report.parsed_command.intent == "no_action"
    assert report.parsed_command.is_inaction

    # Nothing to transmit and nothing to render.
    assert report.normalised_serial is None
    assert report.resolved_pose is None

    # Still a completed run: every stage is recorded, so a model that refuses
    # sensibly is not scored as one that failed to parse.
    assert report.stages_completed == ALL_STAGES


def test_emergency_stop_passes_and_produces_no_pose():
    report = check(response("S"))
    assert report.passed, [i.message for i in report.errors]
    assert report.resolved_pose is None


# ── Stage 1: parse ──────────────────────────────────────────────────────────


def test_prose_with_no_object_is_rejected():
    report = check("I would close the hand for you.")
    assert not report.passed
    assert report.failed_stage is ValidationStage.PARSE


def test_an_empty_response_is_rejected():
    assert not check("").passed
    assert not check("   \n  ").passed


def test_a_bare_command_line_no_longer_satisfies_the_contract():
    """The contract is JSON. A lone `C` is now a parse failure, not a shortcut."""
    report = check("C")
    assert not report.passed
    assert report.failed_stage is ValidationStage.PARSE


@pytest.mark.parametrize("wrapper,expected", [
    ("```json\n{body}\n```", "fenced_code_block"),
    ("Here is my answer:\n{body}\nHope that helps.", "embedded_in_prose"),
])
def test_a_wrapped_object_is_recovered_but_flagged(wrapper, expected):
    """Recovery exists so the metrics can distinguish *how* a model deviates,
    not to be lenient: the run stops counting as clean."""
    raw = wrapper.format(body=response("C"))
    report = check(raw)
    assert report.passed, [i.message for i in report.errors]
    assert any(i.code == "JSON_REQUIRED_REPAIR" for i in report.warnings)
    assert extract_json(raw)[1] == expected


def test_bare_json_needs_no_repair():
    report = check(response("A320"))
    assert not any(i.code == "JSON_REQUIRED_REPAIR" for i in report.issues)


def test_a_nested_object_is_not_cut_short_at_the_first_closing_brace():
    """Brace matching is scanned, not regexed. A regex cannot balance nesting and
    would truncate at the `}` closing the `safety` block, producing a
    syntactically invalid fragment and a misleading parse failure."""
    raw = "Result:\n" + response("A320")
    parsed, note = extract_json(raw)
    assert note == "embedded_in_prose"
    assert parsed["safety"] == {"within_limits": True}
    assert parsed["serial_command"] == "A320"


def test_a_brace_inside_a_string_does_not_end_the_object():
    raw = "Answer: " + response("C", detected_pattern="power_grasp}{")
    parsed, _ = extract_json(raw)
    assert parsed["detected_pattern"] == "power_grasp}{"


# ── Stage 2: schema ─────────────────────────────────────────────────────────


def test_an_unknown_field_is_rejected():
    """`extra="forbid"`: a model inventing fields has not followed the contract,
    and silently dropping them would hide that."""
    report = check(response("C", reasoning="I saw a strong flexor burst"))
    assert not report.passed
    assert report.failed_stage is ValidationStage.SCHEMA


def test_a_missing_serial_command_is_rejected_for_any_acting_intent():
    """Optional only for `no_action`. An intent that moves the hand must say
    how, and omitting it is now a protocol failure rather than a schema one —
    the field parses, it simply describes no command."""
    report = check(json.dumps({"intent": "gesture", "gesture": "C"}))
    assert not report.passed
    assert report.failed_stage is ValidationStage.PROTOCOL


def test_an_invented_intent_is_rejected():
    report = check(response("C", intent="wiggle"))
    assert not report.passed
    assert report.failed_stage is ValidationStage.SCHEMA


def test_confidence_outside_zero_to_one_is_rejected():
    report = check(response("C", confidence=1.4))
    assert not report.passed
    assert report.failed_stage is ValidationStage.SCHEMA


def test_a_declared_hand_is_ignored_entirely():
    """Surface EMG is the same signal whichever hand the device is.

    The electrodes sit on a forearm; nothing in the window says which side the
    prosthesis is fitted to. A model naming one is guessing, so flagging the
    guess as a disagreement reported a discrepancy that could not have been
    anything else — noise on every run from any model that defaults to "right".

    Handedness is a property of the configured hardware, and that is what every
    stage uses.
    """
    report = check(response("C", hand="left"), hand=Handedness.RIGHT)
    assert report.passed
    assert not report.warnings or all(
        issue.code != "HAND_MISMATCH" for issue in report.warnings
    )


def test_a_response_that_omits_the_hand_is_perfectly_valid():
    """It is not a field the signal can support, so it is not required."""
    payload = json.loads(response("C"))
    del payload["hand"]
    assert check(json.dumps(payload)).passed


def test_an_unlisted_pattern_label_is_warned_not_blocked():
    report = check(response("C", detected_pattern="power_squeeze"))
    assert report.passed
    assert any(i.code == "UNKNOWN_PATTERN_LABEL" for i in report.warnings)


def test_an_absent_pattern_label_is_derived_from_the_command():
    """Every execution has to be groupable, including those that omit the label."""
    report = check(response("C", detected_pattern=None))
    assert report.passed
    assert report.parsed_command.detected_pattern == "close"


# ── Stage 3: protocol ───────────────────────────────────────────────────────


def test_an_invented_command_letter_is_rejected():
    report = check(response("Z100", commands=[]))
    assert not report.passed
    assert report.failed_stage is ValidationStage.PROTOCOL


def test_lowercase_is_rejected():
    assert not check(response("a320", commands=[])).passed


def test_a_gesture_cannot_be_mixed_with_positions():
    report = check(response("P,A320", intent="gesture", gesture="P"))
    assert not report.passed
    assert report.failed_stage is ValidationStage.PROTOCOL


def test_an_actuator_cannot_be_addressed_twice():
    assert not check(response("A320,A100")).passed


def test_bare_c_closes_the_hand_and_c400_moves_the_middle_finger():
    """The documented ambiguity, end to end."""
    closed = check(response("C"))
    assert closed.passed
    assert closed.parsed_command.gesture == "C"

    middle = check(response("C400"))
    assert middle.passed, [i.message for i in middle.errors]
    assert middle.parsed_command.gesture is None
    assert middle.parsed_command.commands[0].actuator == "C"


# ── Stage 4: consistency ────────────────────────────────────────────────────


def test_a_gesture_field_disagreeing_with_the_command_is_rejected():
    report = check(response("C", gesture="P"))
    assert not report.passed
    assert report.failed_stage is ValidationStage.CONSISTENCY
    assert any(i.code == "GESTURE_MISMATCH" for i in report.errors)


def test_a_commands_array_disagreeing_with_the_command_is_rejected():
    report = check(response("A320", commands=[
        {"actuator": "A", "position": 500, "speed_pct": 60}
    ]))
    assert not report.passed
    assert any(i.code == "COMMANDS_MISMATCH" for i in report.errors)


@pytest.mark.parametrize("serial", ["A320", "S", "O", "C"])
def test_a_refusal_that_names_any_movement_is_rejected(serial):
    """The contradiction, in every spelling a model has reached for.

    `A320` and `C` are plainly movements. `S` is a halt, which is a decision
    rather than an abstention. `O` opens the hand — the spelling that used to be
    accepted, and the one that drops whatever is being held.

    Rejected with a message that names the fix, because a model told only that
    its answer was wrong will reach for the next-nearest thing.
    """
    report = check(response(serial, intent="no_action", confidence=0.2))
    assert not report.passed
    issue = next(i for i in report.errors if i.code == "NO_ACTION_WITH_COMMAND")
    assert "leave serial_command empty" in issue.message


def test_stop_must_be_declared_as_stop_not_as_a_gesture():
    report = check(response("S", intent="gesture", gesture="S"))
    assert not report.passed
    assert any(i.code == "STOP_DECLARED_AS_GESTURE" for i in report.errors)


def test_a_stop_intent_that_does_not_stop_is_rejected():
    report = check(response("C", intent="stop", gesture="C"))
    assert not report.passed
    assert any(i.code == "STOP_INTENT_WITHOUT_STOP" for i in report.errors)


def test_joint_positions_intent_with_no_positions_is_rejected():
    report = check(response("C", intent="joint_positions", gesture="C", commands=[]))
    assert not report.passed
    assert any(i.code == "INTENT_WITHOUT_POSITIONS" for i in report.errors)


def test_a_confident_refusal_still_passes():
    """High confidence on a refusal is not dangerous — the hand does not move
    either way. It is worth noticing only as a sign the model is not using the
    confidence scale as instructed, which matters when confidence is analysed."""
    report = check(json.dumps({"intent": "no_action", "confidence": 0.99}))
    assert report.passed


# ── Stage 5: range ──────────────────────────────────────────────────────────


def test_a_position_beyond_the_thumb_limit_is_rejected():
    report = check(response("E200"))
    assert not report.passed
    assert report.failed_stage is ValidationStage.RANGE
    assert any(i.code == "POSITION_OUT_OF_RANGE" for i in report.errors)


@pytest.mark.parametrize("command", ["A600", "B550", "C600", "D550", "E130", "F400"])
def test_each_actuator_accepts_its_documented_maximum(command):
    report = check(response(command))
    assert report.passed, [i.message for i in report.errors]


def test_the_same_command_passes_or_fails_by_profile():
    """F380 is legal under Tabla 5 and illegal under the Anexo A envelope, which
    is why the profile is versioned rather than hard-coded."""
    assert check(response("F380"),
                 profile=get_limit_profile(LimitProfileId.TABLE_5_V3)).passed

    strict = check(response("F380"),
                   profile=get_limit_profile(LimitProfileId.ANNEX_A_V3))
    assert not strict.passed
    assert strict.failed_stage is ValidationStage.RANGE


def test_claiming_safety_on_an_out_of_range_command_is_recorded():
    """A model that is wrong is recoverable. A model that is wrong and reports
    itself safe is the failure the system prompt calls dishonesty, and it is
    only visible because the claim and the verdict are stored together."""
    report = check(response("E200", within_limits=True))
    assert not report.passed
    assert any(i.code == "FALSE_SAFETY_ASSERTION" for i in report.issues)


def test_admitting_the_command_is_out_of_range_is_not_flagged_as_dishonest():
    report = check(response("E200", within_limits=False))
    assert not report.passed
    assert not any(i.code == "FALSE_SAFETY_ASSERTION" for i in report.issues)


# ── Stage 7: safety ─────────────────────────────────────────────────────────


def test_an_exclusive_command_cannot_be_combined():
    assert not check(response("S,A320", intent="stop", gesture="S")).passed


def test_collision_risk_is_warned_not_blocked():
    """Severity depends on whether an object is in the grasp, so the useful
    thing is to make the frequency measurable rather than to refuse."""
    report = check(response("C"))
    assert report.passed
    assert any(i.severity is Severity.WARNING for i in report.issues)


def test_a_failed_response_never_produces_a_pose():
    report = check(response("E999"))
    assert not report.passed
    assert report.resolved_pose is None


def test_the_hand_is_never_taken_from_the_response():
    """The configured hand drives the pose, whatever the model declared.

    This is the substantive half of ignoring the field: not merely "no warning"
    but "no influence". A left-hand pose rendered from a right-hand execution
    would be a mirrored grasp on the simulator and on the hardware.
    """
    right = check(response("C", hand="left"), hand=Handedness.RIGHT)
    assert right.resolved_pose.handedness is Handedness.RIGHT

    left = check(response("C", hand="right"), hand=Handedness.LEFT)
    assert left.resolved_pose.handedness is Handedness.LEFT


def test_a_refusal_produces_no_movement_and_so_reaches_no_hardware() -> None:
    """The safety property, traced to the code rather than asserted in prose.

    A `SimulatorMovement` is only built when a pose was resolved, and the
    prosthesis link is fed from broadcast movements. Inaction resolves no pose,
    so there is no movement row, nothing is broadcast, and nothing can be
    transmitted — the hand stays exactly where it was.
    """
    import pathlib

    report = check(json.dumps({"intent": "no_action"}))
    assert report.passed
    assert report.resolved_pose is None

    backend = pathlib.Path(__file__).resolve().parent.parent
    service = (backend / "app" / "services" / "execution_service.py").read_text()
    assert "if report.passed and report.resolved_pose is not None:" in service
    assert "execution.movement = SimulatorMovement(" in service

    endpoint = (backend / "app" / "api" / "v1" / "executions.py").read_text()
    assert "if execution.validation_passed and execution.movement is not None:" in endpoint


def test_a_refusal_is_scored_against_an_expected_command_as_a_miss() -> None:
    """Refusing is a legitimate answer, not a free pass.

    If the window was labelled `C` and the model declined, that is wrong — and
    it has to count as wrong, or a model that refuses everything would score
    perfectly on a labelled set.
    """
    from app.domain.protocol import normalise_expected_command
    from app.services.emg_service import synthesise_window
    from app.services.metrics_service import compute_metrics

    report = check(json.dumps({"intent": "no_action", "confidence": 0.2}))
    assert report.passed

    metrics = compute_metrics(
        report=report, call=None,
        window=synthesise_window("power_grasp", seed=1, samples=8),
        handedness=Handedness.RIGHT, profile=None,
        expected_serial_command=normalise_expected_command("C"),
    )
    assert metrics["command_matches_expected"] is False
    assert metrics["refused_to_act"] is True
