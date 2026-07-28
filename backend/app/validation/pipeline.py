"""Five-stage validation: raw model output -> executable hand pose.

    parse -> protocol -> range -> kinematic -> safety

Nothing reaches the simulator, and later the physical prosthesis, without
clearing every stage. A failure at any point marks the whole execution FAILED,
records the issue with a queryable code, and leaves the hand where it was.

The model now emits the command line itself, so two former stages are gone:
`schema` checked a JSON object against a declared shape, and `consistency`
checked that object against the command line sitting beside it. With one
representation instead of two there is nothing left to disagree.
"""

from __future__ import annotations

import re

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
from app.schemas.llm_output import describe_command
from app.validation.results import (
    Severity,
    ValidationIssue,
    ValidationReport,
    ValidationStage,
)

#: A command line: letters and digits, commas, nothing else.
_COMMAND_RE = re.compile(r"^[A-Z](?:-?\d+)?(?:\s*,\s*[A-Z](?:-?\d+)?)*$")

#: Wrappers a model may put around the answer despite being told not to.
_FENCE_RE = re.compile(r"```[a-z]*\s*(.*?)\s*```", re.DOTALL)
_QUOTED_RE = re.compile(r"[\"\'`]([A-Z][^\"\'`\n]*)[\"\'`]")


# ═════════════════════════════════════════════════════════════════════════════
# Stage 1 - parse
# ═════════════════════════════════════════════════════════════════════════════


def extract_command(raw: str) -> tuple[str | None, str | None]:
    """Recover the command line from whatever the model actually sent.

    A conforming reply is the bare line. Recovery is still attempted for a
    fenced block, a quoted string or a line buried in prose — not to be lenient,
    but so the metrics can distinguish *how* a model deviates. A response that
    needed repair is recorded as such and stops being a clean result, which is
    more informative than collapsing every deviation into one parse failure.
    """
    if not raw or not raw.strip():
        return None, "Empty response."

    text = raw.strip()

    if _COMMAND_RE.match(text):
        return text, None

    fenced = _FENCE_RE.search(text)
    if fenced and _COMMAND_RE.match(fenced.group(1).strip()):
        return fenced.group(1).strip(), "fenced_code_block"

    quoted = _QUOTED_RE.search(text)
    if quoted and _COMMAND_RE.match(quoted.group(1).strip()):
        return quoted.group(1).strip(), "quoted_string"

    # A single command line somewhere in a longer reply.
    for line in (ln.strip().rstrip(".") for ln in text.splitlines()):
        if line and _COMMAND_RE.match(line):
            return line, "embedded_in_prose"

    return None, (
        "No serial command could be recovered. The reply must be one line "
        "containing only the command."
    )


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
    line, note = extract_command(raw_response)
    if line is None:
        report.add(ValidationIssue(
            ValidationStage.PARSE, "NO_COMMAND",
            note or "No command in the response.",
            context={"raw_preview": (raw_response or "")[:500]},
        ))
        return _finish(report)

    if note:
        report.add(ValidationIssue(
            ValidationStage.PARSE, "COMMAND_REQUIRED_REPAIR",
            f"The reply was not a bare command line ({note}); it had to be extracted.",
            severity=Severity.WARNING,
            context={"recovered": line},
        ))
    report.stages_completed.append(ValidationStage.PARSE)

    # ── Stage 2: protocol ───────────────────────────────────────────────────
    try:
        frame: SerialFrame = parse_serial_command(line)
    except ProtocolError as exc:
        report.add(ValidationIssue(
            ValidationStage.PROTOCOL, "MALFORMED_SERIAL", str(exc),
            context={"command": line},
        ))
        return _finish(report)

    report.stages_completed.append(ValidationStage.PROTOCOL)
    report.normalised_serial = frame.encode()
    report.parsed_command = describe_command(frame, expected_hand)

    # ── Stage 3: range ──────────────────────────────────────────────────────
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
    if report.errors:
        return _finish(report)
    report.stages_completed.append(ValidationStage.RANGE)

    # ── Stage 4: kinematic reachability ─────────────────────────────────────
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

    # ── Stage 5: safety ─────────────────────────────────────────────────────
    _check_safety(report, frame, pose)
    if report.errors:
        return _finish(report)
    report.stages_completed.append(ValidationStage.SAFETY)

    report.passed = True
    return report


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
