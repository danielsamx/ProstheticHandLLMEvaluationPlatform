"""Seven-stage validation pipeline: raw LLM text -> executable hand pose.

Nothing reaches the simulator (and, later, the physical prosthesis) without
clearing every stage.  A failure at any stage marks the whole execution as
FAILED, records the issue and leaves the simulator untouched.

    parse -> schema -> protocol -> consistency -> range -> kinematic -> safety
"""

from __future__ import annotations

import json
import re
from typing import Any

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
from app.domain.protocol import ProtocolError, parse_serial_command
from app.schemas.llm_output import ProstheticCommand
from app.validation.results import (
    Severity,
    ValidationIssue,
    ValidationReport,
    ValidationStage,
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


# ═════════════════════════════════════════════════════════════════════════════
# Stage 1 - parse
# ═════════════════════════════════════════════════════════════════════════════


def extract_json(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Best-effort JSON extraction.

    A conforming model returns bare JSON.  We still tolerate a fenced block or
    surrounding prose so that *why* a model failed is visible in the metrics
    (``json_required_repair``) instead of collapsing every deviation into a
    single opaque parse error.
    """
    if raw is None:
        return None, "Empty response."
    text = raw.strip()
    if not text:
        return None, "Empty response."

    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        pass

    fenced = _FENCE_RE.search(text)
    if fenced:
        try:
            return json.loads(fenced.group(1)), "fenced_code_block"
        except json.JSONDecodeError:
            pass

    obj = _OBJECT_RE.search(text)
    if obj:
        try:
            return json.loads(obj.group(0)), "embedded_object"
        except json.JSONDecodeError:
            pass

    return None, "Response is not valid JSON and no JSON object could be recovered."


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
            ValidationStage.PARSE, "INVALID_JSON",
            note or "Response is not valid JSON.",
            context={"raw_preview": (raw_response or "")[:500]},
        ))
        return _finish(report)
    if note:
        report.add(ValidationIssue(
            ValidationStage.PARSE, "JSON_REQUIRED_REPAIR",
            f"Model did not return bare JSON ({note}); the payload had to be extracted.",
            severity=Severity.WARNING,
        ))
    if not isinstance(payload, dict):
        report.add(ValidationIssue(
            ValidationStage.PARSE, "NOT_AN_OBJECT",
            f"Top-level JSON value is {type(payload).__name__}, expected an object.",
        ))
        return _finish(report)
    report.stages_completed.append(ValidationStage.PARSE)

    # ── Stage 2: schema ─────────────────────────────────────────────────────
    try:
        command = ProstheticCommand.model_validate(payload)
    except ValidationError as exc:
        for err in exc.errors():
            report.add(ValidationIssue(
                ValidationStage.SCHEMA,
                str(err.get("type", "schema_error")).upper(),
                str(err.get("msg", "Schema violation.")),
                field_path=".".join(str(p) for p in err.get("loc", ())) or None,
                context={"input": _truncate(err.get("input"))},
            ))
        return _finish(report)
    report.parsed_command = command
    report.stages_completed.append(ValidationStage.SCHEMA)

    if command.handedness is not expected_hand:
        report.add(ValidationIssue(
            ValidationStage.SCHEMA, "HAND_MISMATCH",
            f"Model targeted the {command.hand} hand but the experiment requested "
            f"{expected_hand.value}.",
            field_path="hand",
        ))
        return _finish(report)

    # ── Stage 3: protocol ───────────────────────────────────────────────────
    frame = None
    if command.intent != "no_action":
        try:
            frame = parse_serial_command(command.serial_command)
        except ProtocolError as exc:
            report.add(ValidationIssue(
                ValidationStage.PROTOCOL, "MALFORMED_SERIAL",
                str(exc), field_path="serial_command",
                context={"serial_command": command.serial_command},
            ))
            return _finish(report)
    report.stages_completed.append(ValidationStage.PROTOCOL)

    # ── Stage 4: consistency between structured fields and the wire frame ───
    if frame is not None:
        _check_consistency(report, command, frame)
        if report.errors:
            return _finish(report)
    report.stages_completed.append(ValidationStage.CONSISTENCY)
    if frame is not None:
        report.normalised_serial = frame.encode()

    # ── Stage 5: range ──────────────────────────────────────────────────────
    positions: dict[Actuator, int] = {}
    if command.intent == "joint_positions":
        for cmd in command.commands:
            actuator = cmd.actuator_enum
            lo, hi = profile.bounds(actuator)
            if not profile.contains(actuator, cmd.position):
                report.add(ValidationIssue(
                    ValidationStage.RANGE, "POSITION_OUT_OF_RANGE",
                    f"Actuator {actuator.value} ({ACTUATORS[actuator].label}) commanded to "
                    f"{cmd.position}, outside the documented range {lo}-{hi} "
                    f"of profile {profile.id.value}.",
                    field_path=f"commands[{actuator.value}].position",
                    context={"actuator": actuator.value, "position": cmd.position,
                             "min": lo, "max": hi},
                ))
            positions[actuator] = cmd.position
        if report.errors:
            return _finish(report)
    report.stages_completed.append(ValidationStage.RANGE)

    # ── Stage 6: kinematic reachability ─────────────────────────────────────
    pose: HandPose | None = None
    if command.intent == "joint_positions":
        pose = pose_from_positions(
            positions,
            handedness=expected_hand,
            profile=profile,
            previous=previous_positions,
            speed_pct=min((c.speed_pct for c in command.commands), default=SAFETY.default_speed_pct),
        )
    elif command.intent in ("gesture", "stop"):
        gesture_cmd = ControlCommand(command.gesture or ControlCommand.STOP.value)
        pose = pose_from_gesture(gesture_cmd, handedness=expected_hand, profile=profile)

    if pose is not None:
        for joint_state in pose.joints:
            joint = JOINTS_BY_ID[joint_state.joint_id]
            if not (joint.min_flexion_deg - 1e-6 <= joint_state.angle_deg <= joint.max_flexion_deg + 1e-6):
                report.add(ValidationIssue(
                    ValidationStage.KINEMATIC, "JOINT_LIMIT_EXCEEDED",
                    f"Joint {joint.id} would reach {joint_state.angle_deg:.1f} deg, outside "
                    f"its mechanical range {joint.min_flexion_deg:.0f}-{joint.max_flexion_deg:.0f} deg.",
                    context={"joint": joint.id, "angle_deg": joint_state.angle_deg},
                ))
        if report.errors:
            return _finish(report)
    report.resolved_pose = pose
    report.stages_completed.append(ValidationStage.KINEMATIC)

    # ── Stage 7: safety ─────────────────────────────────────────────────────
    _check_safety(report, command, pose, profile)
    if report.errors:
        return _finish(report)
    report.stages_completed.append(ValidationStage.SAFETY)

    report.passed = True
    return report


# ═════════════════════════════════════════════════════════════════════════════
# Stage helpers
# ═════════════════════════════════════════════════════════════════════════════


def _check_consistency(report: ValidationReport, command: ProstheticCommand, frame) -> None:
    """The serial line and the structured fields must describe the same motion."""
    if command.intent in ("gesture", "stop"):
        controls = frame.controls
        if len(controls) != 1:
            report.add(ValidationIssue(
                ValidationStage.CONSISTENCY, "SERIAL_NOT_A_GESTURE",
                f"intent='{command.intent}' but serial_command {frame.raw!r} is not a "
                "single preset gesture letter.",
                field_path="serial_command",
            ))
            return
        if controls[0].value != command.gesture:
            report.add(ValidationIssue(
                ValidationStage.CONSISTENCY, "GESTURE_SERIAL_MISMATCH",
                f"gesture='{command.gesture}' but serial_command encodes "
                f"'{controls[0].value}'.",
                field_path="serial_command",
            ))
        return

    if command.intent == "joint_positions":
        if frame.controls:
            report.add(ValidationIssue(
                ValidationStage.CONSISTENCY, "UNEXPECTED_GESTURE_IN_SERIAL",
                f"intent='joint_positions' but serial_command {frame.raw!r} contains a "
                "preset gesture letter.",
                field_path="serial_command",
            ))
            return
        wire = frame.positions
        structured = {c.actuator_enum: c.position for c in command.commands}
        if wire != structured:
            report.add(ValidationIssue(
                ValidationStage.CONSISTENCY, "COMMANDS_SERIAL_MISMATCH",
                "serial_command does not match the 'commands' array.",
                field_path="serial_command",
                context={
                    "serial": {a.value: p for a, p in wire.items()},
                    "commands": {a.value: p for a, p in structured.items()},
                },
            ))


def _check_safety(
    report: ValidationReport,
    command: ProstheticCommand,
    pose: HandPose | None,
    profile: LimitProfile,
) -> None:
    # Exclusivity of system commands.
    if command.gesture is not None:
        gesture_cmd = ControlCommand(command.gesture)
        if gesture_cmd in EXCLUSIVE_COMMANDS and command.commands:
            report.add(ValidationIssue(
                ValidationStage.SAFETY, "EXCLUSIVE_COMMAND_COMBINED",
                f"{gesture_cmd.value} must be transmitted alone.",
                field_path="gesture",
            ))
        if gesture_cmd not in GESTURES:
            report.add(ValidationIssue(
                ValidationStage.SAFETY, "UNKNOWN_GESTURE",
                f"Gesture {gesture_cmd.value!r} is not implemented in the firmware.",
                field_path="gesture",
            ))

    # Simultaneous actuator budget.
    if len(command.commands) > SAFETY.max_simultaneous_actuators:
        report.add(ValidationIssue(
            ValidationStage.SAFETY, "TOO_MANY_ACTUATORS",
            f"{len(command.commands)} actuators commanded at once; the hardware "
            f"supports at most {SAFETY.max_simultaneous_actuators}.",
            field_path="commands",
        ))

    # Speed envelope.
    for cmd in command.commands:
        if not (SAFETY.min_speed_pct <= cmd.speed_pct <= SAFETY.max_speed_pct):
            report.add(ValidationIssue(
                ValidationStage.SAFETY, "SPEED_OUT_OF_RANGE",
                f"Actuator {cmd.actuator} speed {cmd.speed_pct}% is outside "
                f"{SAFETY.min_speed_pct}-{SAFETY.max_speed_pct}%.",
                field_path=f"commands[{cmd.actuator}].speed_pct",
            ))

    # Thumb / palm collision heuristic: a fully opposed thumb driven into a
    # fully closed middle finger crushes the digits against each other.
    if pose is not None:
        norm = pose.actuator_normalised
        thumb_rot = norm.get(Actuator.E_THUMB_LOWER.value, 0.0)
        thumb_flex = norm.get(Actuator.F_THUMB_UPPER.value, 0.0)
        middle = norm.get(Actuator.C_MIDDLE.value, 0.0)
        index = norm.get(Actuator.D_INDEX.value, 0.0)
        if thumb_rot > 0.95 and thumb_flex > 0.95 and max(middle, index) > 0.95:
            report.add(ValidationIssue(
                ValidationStage.SAFETY, "DIGIT_COLLISION_RISK",
                "Thumb fully opposed and fully flexed against a fully flexed "
                "index/middle finger: the digits would collide.",
                severity=Severity.WARNING,
                context={"E": thumb_rot, "F": thumb_flex, "C": middle, "D": index},
            ))

    # Duration plausibility.
    if pose is not None and command.estimated_duration_ms > 0:
        drift = abs(command.estimated_duration_ms - pose.duration_ms)
        if drift > max(500, pose.duration_ms):
            report.add(ValidationIssue(
                ValidationStage.SAFETY, "DURATION_IMPLAUSIBLE",
                f"Model estimated {command.estimated_duration_ms} ms; kinematic model "
                f"predicts {pose.duration_ms} ms.",
                severity=Severity.WARNING,
                field_path="estimated_duration_ms",
            ))

    # Self-assessment honesty check (recorded as a metric, not a blocker).
    if command.safety.within_limits is False:
        report.add(ValidationIssue(
            ValidationStage.SAFETY, "MODEL_SELF_REPORTED_UNSAFE",
            "Model emitted a command while reporting safety.within_limits=false.",
            severity=Severity.WARNING,
            field_path="safety.within_limits",
        ))


def _finish(report: ValidationReport) -> ValidationReport:
    report.passed = not report.errors
    return report


def _truncate(value: Any, limit: int = 200) -> Any:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."
