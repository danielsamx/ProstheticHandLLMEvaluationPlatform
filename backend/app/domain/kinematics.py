"""Forward kinematics: encoder positions -> joint angles for the 3D simulator.

The HANDi fingers are tendon driven: one gearmotor flexes an entire finger
chain, so joint angles are a fixed coupled function of the actuator's
normalised travel.  This module turns a validated command set into the joint
angle map the Angular/Three.js simulator consumes, and provides the inverse
mapping used to render firmware preset gestures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.hand_spec import (
    ACTUATORS,
    GESTURES,
    JOINTS,
    JOINTS_BY_ACTUATOR,
    SAFETY,
    Actuator,
    ControlCommand,
    Handedness,
    LimitProfile,
    get_limit_profile,
)


@dataclass(slots=True)
class JointState:
    """Resolved angle of one kinematic joint."""

    joint_id: str
    digit: str
    joint_type: str
    angle_deg: float
    normalised: float
    driven_by: str


@dataclass(slots=True)
class HandPose:
    """A complete, physically realisable pose ready for rendering."""

    handedness: Handedness
    limit_profile: str
    actuator_positions: dict[str, int] = field(default_factory=dict)
    actuator_normalised: dict[str, float] = field(default_factory=dict)
    joints: list[JointState] = field(default_factory=list)
    duration_ms: int = SAFETY.min_move_duration_ms
    source: str = "positions"

    def to_dict(self) -> dict:
        return {
            "handedness": self.handedness.value,
            "limit_profile": self.limit_profile,
            "actuator_positions": self.actuator_positions,
            "actuator_normalised": self.actuator_normalised,
            "joints": [
                {
                    "joint_id": j.joint_id,
                    "digit": j.digit,
                    "joint_type": j.joint_type,
                    "angle_deg": round(j.angle_deg, 3),
                    "normalised": round(j.normalised, 4),
                    "driven_by": j.driven_by,
                }
                for j in self.joints
            ],
            "duration_ms": self.duration_ms,
            "source": self.source,
        }


def _joint_states(normalised: dict[Actuator, float]) -> list[JointState]:
    states: list[JointState] = []
    for joint in JOINTS:
        travel = normalised.get(joint.driven_by, 0.0)
        effective = max(0.0, min(1.0, travel * joint.coupling))
        angle = joint.min_flexion_deg + effective * joint.range_deg
        states.append(
            JointState(
                joint_id=joint.id,
                digit=joint.digit.value,
                joint_type=joint.joint_type.value,
                angle_deg=angle,
                normalised=effective,
                driven_by=joint.driven_by.value,
            )
        )
    return states


def pose_from_positions(
    positions: dict[Actuator, int],
    *,
    handedness: Handedness = Handedness.RIGHT,
    profile: LimitProfile | None = None,
    previous: dict[Actuator, int] | None = None,
    speed_pct: int = SAFETY.default_speed_pct,
) -> HandPose:
    """Build a :class:`HandPose` from raw encoder targets.

    Actuators not mentioned keep their previous position (or 0 if unknown),
    mirroring the firmware, which only moves the motors it was told about.
    """
    profile = profile or get_limit_profile()
    previous = previous or {}

    resolved: dict[Actuator, int] = {}
    for actuator in Actuator:
        if actuator in positions:
            resolved[actuator] = int(positions[actuator])
        else:
            resolved[actuator] = int(previous.get(actuator, profile.bounds(actuator)[0]))

    normalised = {a: profile.normalise(a, p) for a, p in resolved.items()}

    return HandPose(
        handedness=handedness,
        limit_profile=profile.id.value,
        actuator_positions={a.value: p for a, p in resolved.items()},
        actuator_normalised={a.value: round(n, 4) for a, n in normalised.items()},
        joints=_joint_states(normalised),
        duration_ms=estimate_duration_ms(resolved, previous, profile, speed_pct),
        source="positions",
    )


def pose_from_gesture(
    command: ControlCommand,
    *,
    handedness: Handedness = Handedness.RIGHT,
    profile: LimitProfile | None = None,
) -> HandPose | None:
    """Materialise a firmware preset gesture into a renderable pose.

    Returns ``None`` for system commands (S / X / I) that do not define a pose.
    """
    profile = profile or get_limit_profile()
    gesture = GESTURES[command]
    if gesture.pose is None:
        return None

    normalised = {a: max(0.0, min(1.0, v)) for a, v in gesture.pose.items()}
    positions: dict[Actuator, int] = {}
    for actuator, value in normalised.items():
        lo, hi = profile.bounds(actuator)
        positions[actuator] = int(round(lo + value * (hi - lo)))

    return HandPose(
        handedness=handedness,
        limit_profile=profile.id.value,
        actuator_positions={a.value: p for a, p in positions.items()},
        actuator_normalised={a.value: round(v, 4) for a, v in normalised.items()},
        joints=_joint_states(normalised),
        duration_ms=gesture.typical_duration_ms,
        source=f"gesture:{gesture.name}",
    )


def estimate_duration_ms(
    target: dict[Actuator, int],
    previous: dict[Actuator, int] | None,
    profile: LimitProfile,
    speed_pct: int = SAFETY.default_speed_pct,
) -> int:
    """Estimate travel time for the slowest actuator in the command set."""
    previous = previous or {}
    speed = max(SAFETY.min_speed_pct, min(SAFETY.max_speed_pct, speed_pct))
    counts_per_second = SAFETY.max_counts_per_second * (speed / 100.0)
    if counts_per_second <= 0:
        return SAFETY.max_move_duration_ms

    worst = 0.0
    for actuator, position in target.items():
        start = previous.get(actuator, profile.bounds(actuator)[0])
        worst = max(worst, abs(position - start))

    millis = int(round(worst / counts_per_second * 1000.0))
    return max(SAFETY.min_move_duration_ms, min(SAFETY.max_move_duration_ms, millis))


def rest_pose(
    handedness: Handedness = Handedness.RIGHT,
    profile: LimitProfile | None = None,
) -> HandPose:
    """The neutral OPEN pose the hand must return to at the end of a session."""
    profile = profile or get_limit_profile()
    pose = pose_from_gesture(ControlCommand.OPEN, handedness=handedness, profile=profile)
    assert pose is not None  # OPEN always defines a pose
    return pose


def actuator_joint_map() -> dict[str, list[str]]:
    """Actuator letter -> joint ids it drives (exported to the frontend)."""
    return {a.value: [j.id for j in joints] for a, joints in JOINTS_BY_ACTUATOR.items()}


def describe_kinematics() -> str:
    """Compact kinematic summary for the technical-context prompt block."""
    lines = []
    for actuator, spec in ACTUATORS.items():
        joints = JOINTS_BY_ACTUATOR[actuator]
        detail = ", ".join(
            f"{j.id}({j.joint_type.value}) 0-{j.max_flexion_deg:.0f}deg x{j.coupling:.2f}"
            for j in joints
        )
        lines.append(f"  {actuator.value} -> {spec.digit.value} {spec.label}: {detail}")
    return "\n".join(lines)
