"""Seven-stage validation: raw model output -> executable hand pose.

    parse -> schema -> protocol -> consistency -> range -> kinematic -> safety

Nothing reaches the simulator, and later the physical prosthesis, without
clearing every stage. A failure at any point marks the whole execution FAILED,
records the issue with a queryable code, and leaves the hand where it was.

The stages are deliberately narrow. A single "is this response valid" check
would answer yes or no; seven named gates answer *where* a model breaks down,
and that is the measurement this platform is built to produce. A model that
always emits well-formed JSON but routinely exceeds a mechanical stop fails
differently from one that cannot produce JSON at all, and lumping the two
together would erase the distinction that matters clinically.

`consistency` is the stage that only exists because the response carries the
same decision twice. It is not redundant bookkeeping: a `serial_command` of
`A320` sitting beside `intent: "no_action"` is a model that has contradicted
itself, and executing either half would be executing something the model did
not, as a whole, decide.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from app.domain.hand_spec import (
    ACTUATORS,
    EXCLUSIVE_COMMANDS,
    GESTURES,
    JOINTS_BY_ID,
    SAFETY,
    Actuator,
    ControlCommand,
    Handedness,
    LimitProfile,
    get_limit_profile,
)
from app.domain.kinematics import HandPose, pose_from_gesture, pose_from_positions
from app.domain.protocol import ProtocolError, SerialFrame, parse_serial_command
from app.schemas.llm_output import (
    DETECTED_PATTERNS,
    ProstheticCommand,
    derive_pattern,
)
from app.validation.results import (
    Severity,
    ValidationIssue,
    ValidationReport,
    ValidationStage,
)

#: Wrappers a model may put around the answer despite being told not to.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


# ═════════════════════════════════════════════════════════════════════════════
# Stage 1 - parse
# ═════════════════════════════════════════════════════════════════════════════


def extract_json(raw: str) -> tuple[dict | None, str | None]:
    """Recover the JSON object from whatever the model actually sent.

    A conforming reply parses directly. Recovery is still attempted for a fenced
    block or an object embedded in prose — not to be lenient, but so the metrics
    can distinguish *how* a model deviates. A response that needed repair is
    recorded as such and stops counting as clean, which is more informative than
    collapsing every deviation into one parse failure.

    Returns ``(object, repair_note)``; the note is ``None`` when the reply was
    already conforming, and on failure the object is ``None`` and the note is
    the reason.
    """
    if not raw or not raw.strip():
        return None, "Empty response."

    text = raw.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, None
    except json.JSONDecodeError:
        pass

    fenced = _FENCE_RE.search(text)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, dict):
                return parsed, "fenced_code_block"
        except json.JSONDecodeError:
            pass

    # An object somewhere inside a longer reply. Braces are matched by scanning
    # rather than by regex, because a regex cannot balance nesting and would cut
    # the object short at the first inner `}`.
    start = text.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:index + 1])
                        if isinstance(parsed, dict):
                            return parsed, "embedded_in_prose"
                    except json.JSONDecodeError:
                        pass
                    break

    return None, "No JSON object could be recovered from the response."


# ═════════════════════════════════════════════════════════════════════════════
# Pipeline
# ═════════════════════════════════════════════════════════════════════════════


def validate_response(
    raw_response: str,
    *,
    expected_hand: Handedness,
    limit_profile: LimitProfile | None = None,
    previous_positions: dict[Actuator, int] | None = None,
) -> ValidationReport:
    """Run every stage. Returns a report; never raises for model misbehaviour."""
    profile = limit_profile or get_limit_profile()
    report = ValidationReport(limit_profile=profile.id.value)

    # ── Stage 1: parse ──────────────────────────────────────────────────────
    payload, note = extract_json(raw_response)
    if payload is None:
        report.add(ValidationIssue(
            ValidationStage.PARSE, "NOT_JSON",
            note or "The response is not a JSON object.",
            context={"raw_preview": (raw_response or "")[:500]},
        ))
        return _finish(report)

    if note:
        report.add(ValidationIssue(
            ValidationStage.PARSE, "JSON_REQUIRED_REPAIR",
            f"The reply was not bare JSON ({note}); the object had to be extracted.",
            severity=Severity.WARNING,
            context={"recovered_via": note},
        ))
    report.stages_completed.append(ValidationStage.PARSE)

    # ── Stage 2: schema ─────────────────────────────────────────────────────
    try:
        command = ProstheticCommand.model_validate(payload)
    except ValidationError as exc:
        for error in exc.errors():
            path = ".".join(str(part) for part in error["loc"])
            report.add(ValidationIssue(
                ValidationStage.SCHEMA, "SCHEMA_VIOLATION",
                f"{path or 'response'}: {error['msg']}",
                field_path=path or None,
                context={"type": error["type"]},
            ))
        return _finish(report)

    report.stages_completed.append(ValidationStage.SCHEMA)
    report.parsed_command = command

    # No check on `command.hand`. Surface EMG is the same signal whichever hand
    # the device is, so a model naming one is guessing, and a warning about that
    # guess told the researcher nothing they could act on. The configured hand
    # is authoritative and is what every stage below uses.

    if command.detected_pattern and command.detected_pattern not in DETECTED_PATTERNS:
        report.add(ValidationIssue(
            ValidationStage.SCHEMA, "UNKNOWN_PATTERN_LABEL",
            f"detected_pattern={command.detected_pattern!r} is not one of the "
            "labels the system prompt enumerates.",
            severity=Severity.WARNING,
            field_path="detected_pattern",
            context={"value": command.detected_pattern},
        ))

    # ── Stage 3: protocol ───────────────────────────────────────────────────
    try:
        frame: SerialFrame = parse_serial_command(command.serial_command)
    except ProtocolError as exc:
        report.add(ValidationIssue(
            ValidationStage.PROTOCOL, "MALFORMED_SERIAL", str(exc),
            field_path="serial_command",
            context={"command": command.serial_command},
        ))
        return _finish(report)

    report.stages_completed.append(ValidationStage.PROTOCOL)
    report.normalised_serial = frame.encode()

    # ── Stage 4: consistency ────────────────────────────────────────────────
    _check_consistency(report, command, frame)
    if report.errors:
        return _finish(report)
    report.stages_completed.append(ValidationStage.CONSISTENCY)

    # ── Stage 5: range ──────────────────────────────────────────────────────
    positions = frame.positions
    for actuator, position in positions.items():
        low, high = profile.bounds(actuator)
        if not profile.contains(actuator, position):
            report.add(ValidationIssue(
                ValidationStage.RANGE, "POSITION_OUT_OF_RANGE",
                f"Actuator {actuator.value} ({ACTUATORS[actuator].label}) commanded to "
                f"{position}, outside the documented range {low}-{high} of profile "
                f"{profile.id.value}.",
                field_path=f"command.{actuator.value}",
                context={"actuator": actuator.value, "position": position,
                         "min": low, "max": high},
            ))

    # A model that drove an actuator past a mechanical stop *and* reported the
    # pose as within limits has done something worse than getting it wrong. The
    # system prompt calls this out explicitly, so it is recorded explicitly.
    if report.errors and command.safety is not None and command.safety.within_limits:
        report.add(ValidationIssue(
            ValidationStage.RANGE, "FALSE_SAFETY_ASSERTION",
            "The response asserts within_limits=true for a command that exceeds "
            "a documented range.",
            severity=Severity.WARNING,
            field_path="safety.within_limits",
        ))

    if report.errors:
        return _finish(report)
    report.stages_completed.append(ValidationStage.RANGE)

    # ── Stage 6: kinematic reachability ─────────────────────────────────────
    pose: HandPose | None = None
    if positions:
        pose = pose_from_positions(
            positions, handedness=expected_hand, profile=profile,
            previous=previous_positions,
        )
    elif frame.controls:
        pose = pose_from_gesture(frame.controls[0], handedness=expected_hand, profile=profile)

    if pose is not None:
        for state in pose.joints:
            joint = JOINTS_BY_ID[state.joint_id]
            if not (joint.min_flexion_deg - 1e-6
                    <= state.angle_deg
                    <= joint.max_flexion_deg + 1e-6):
                report.add(ValidationIssue(
                    ValidationStage.KINEMATIC, "JOINT_LIMIT_EXCEEDED",
                    f"Joint {joint.id} would reach {state.angle_deg:.1f} deg, outside its "
                    f"mechanical range {joint.min_flexion_deg:.0f}-"
                    f"{joint.max_flexion_deg:.0f} deg.",
                    context={"joint": joint.id, "angle_deg": state.angle_deg},
                ))
        if report.errors:
            return _finish(report)

    report.resolved_pose = pose
    report.stages_completed.append(ValidationStage.KINEMATIC)

    # ── Stage 7: safety ─────────────────────────────────────────────────────
    _check_safety(report, frame, pose)
    if report.errors:
        return _finish(report)
    report.stages_completed.append(ValidationStage.SAFETY)

    report.passed = True
    return report


# ═════════════════════════════════════════════════════════════════════════════
# Stage implementations
# ═════════════════════════════════════════════════════════════════════════════


def _check_consistency(
    report: ValidationReport, command: ProstheticCommand, frame: SerialFrame
) -> None:
    """The two halves of the response must describe the same decision.

    Every check here compares the model's own words against its own command.
    None of them can be resolved by preferring one side: the point is that the
    model contradicted itself, and picking a winner would silently execute
    something it never coherently decided.
    """
    gesture = frame.controls[0] if frame.controls else None
    positions = frame.positions

    # ── intent vs. what the command actually is ─────────────────────────────
    if command.intent == "gesture":
        if gesture is None:
            report.add(ValidationIssue(
                ValidationStage.CONSISTENCY, "INTENT_WITHOUT_GESTURE",
                f"intent='gesture' but serial_command {command.serial_command!r} "
                "carries positions, not a gesture.",
                field_path="intent",
            ))
        elif gesture is ControlCommand.STOP:
            report.add(ValidationIssue(
                ValidationStage.CONSISTENCY, "STOP_DECLARED_AS_GESTURE",
                "serial_command is S; intent must be 'stop', not 'gesture'.",
                field_path="intent",
            ))
    elif command.intent == "stop":
        if gesture is not ControlCommand.STOP:
            report.add(ValidationIssue(
                ValidationStage.CONSISTENCY, "STOP_INTENT_WITHOUT_STOP",
                f"intent='stop' but serial_command is {command.serial_command!r}, "
                "not S.",
                field_path="intent",
            ))
    elif command.intent == "joint_positions":
        if not positions:
            report.add(ValidationIssue(
                ValidationStage.CONSISTENCY, "INTENT_WITHOUT_POSITIONS",
                f"intent='joint_positions' but serial_command "
                f"{command.serial_command!r} carries no positions.",
                field_path="intent",
            ))
    elif command.intent == "no_action":
        # `O` holds the hand open and is the documented way to say "do nothing".
        # Anything that moves an actuator is not inaction.
        if positions or (gesture is not None and gesture is not ControlCommand.OPEN):
            report.add(ValidationIssue(
                ValidationStage.CONSISTENCY, "NO_ACTION_THAT_ACTS",
                f"intent='no_action' but serial_command {command.serial_command!r} "
                "commands a movement.",
                field_path="intent",
            ))

    # ── gesture field vs. the command letter ────────────────────────────────
    declared = command.gesture
    actual = gesture.value if gesture is not None else None
    if declared != actual:
        report.add(ValidationIssue(
            ValidationStage.CONSISTENCY, "GESTURE_MISMATCH",
            f"gesture={declared!r} but serial_command {command.serial_command!r} "
            f"resolves to {actual!r}.",
            field_path="gesture",
            context={"declared": declared, "actual": actual},
        ))

    # ── commands[] vs. the positions on the wire ────────────────────────────
    declared_positions = {entry.actuator: entry.position for entry in command.commands}
    actual_positions = {a.value: p for a, p in positions.items()}
    if declared_positions != actual_positions:
        report.add(ValidationIssue(
            ValidationStage.CONSISTENCY, "COMMANDS_MISMATCH",
            "The commands array does not match serial_command: "
            f"{declared_positions} vs {actual_positions}.",
            field_path="commands",
            context={"declared": declared_positions, "actual": actual_positions},
        ))

    # ── the model's stated confidence vs. its own refusal ───────────────────
    # The system prompt asks for no_action to come with low confidence. High
    # confidence on a refusal is not dangerous, but it is a sign the model is
    # not using the scale as instructed, which matters when confidence is being
    # analysed as a variable.
    if command.intent == "no_action" and command.confidence > 0.8:
        report.add(ValidationIssue(
            ValidationStage.CONSISTENCY, "CONFIDENT_REFUSAL",
            f"intent='no_action' reported with confidence {command.confidence:.2f}; "
            "the contract asks for low confidence on a refusal.",
            severity=Severity.WARNING,
            field_path="confidence",
        ))

    if command.detected_pattern is None:
        command.detected_pattern = derive_pattern(gesture)


def _check_safety(report: ValidationReport, frame: SerialFrame, pose: HandPose | None) -> None:
    """Rules the protocol parser cannot express on its own."""
    for command in frame.controls:
        if command not in GESTURES:
            report.add(ValidationIssue(
                ValidationStage.SAFETY, "UNKNOWN_GESTURE",
                f"Gesture {command.value!r} is not implemented in the firmware.",
            ))
        if command in EXCLUSIVE_COMMANDS and len(frame.tokens) > 1:
            report.add(ValidationIssue(
                ValidationStage.SAFETY, "EXCLUSIVE_COMMAND_COMBINED",
                f"{command.value} must be transmitted alone.",
            ))

    if len(frame.positions) > SAFETY.max_simultaneous_actuators:
        report.add(ValidationIssue(
            ValidationStage.SAFETY, "TOO_MANY_ACTUATORS",
            f"{len(frame.positions)} actuators commanded at once; the hardware "
            f"supports at most {SAFETY.max_simultaneous_actuators}.",
        ))

    # A fully opposed and fully flexed thumb driven into a fully flexed index or
    # middle finger crushes the digits together. Recorded rather than blocked:
    # the severity depends on whether an object is in the grasp, so the useful
    # thing is to make the frequency measurable per model.
    if pose is not None:
        norm = pose.actuator_normalised
        thumb_rotation = norm.get(Actuator.E_THUMB_LOWER.value, 0.0)
        thumb_flexion = norm.get(Actuator.F_THUMB_UPPER.value, 0.0)
        opposing = max(
            norm.get(Actuator.C_MIDDLE.value, 0.0),
            norm.get(Actuator.D_INDEX.value, 0.0),
        )
        if thumb_rotation > 0.95 and thumb_flexion > 0.95 and opposing > 0.95:
            report.add(ValidationIssue(
                ValidationStage.SAFETY, "DIGIT_COLLISION_RISK",
                "Thumb fully opposed and fully flexed against a fully flexed "
                "index or middle finger: the digits would collide.",
                severity=Severity.WARNING,
                context={"E": thumb_rotation, "F": thumb_flexion, "opposing": opposing},
            ))


def _finish(report: ValidationReport) -> ValidationReport:
    report.passed = not report.errors
    return report
