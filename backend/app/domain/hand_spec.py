"""HANDi EPN V3 prosthetic hand - mechanical & protocol specification.

Derived from the technical manuals during development.  Frozen into code so that
every experiment runs against an identical, reproducible hardware description.

Hardware summary
----------------
* Controller ....... ESP32 (Wemos D1 R32 form factor) + 2x Adafruit Motor Shield V3
* Actuators ........ 5x Pololu Micro Metal Gearmotor 380:1 HPCB 6V with magnetic
                     encoders (12 CPR) + 1x MG90S micro servo (thumb rotation)
* Driven DOF ....... 6 (one per serial command letter A-F)
* Sensors .......... 11x rotary potentiometers (joint angle), 5x FSR (fingertip force)
* Multiplexer ...... CD74HC4067 (16:1), potentiometers on channels C5..C15
* Signal cond. ..... LM324 (quad op-amp) + LM358 (dual op-amp), 5x 15k resistors
* Link ............. Bluetooth SPP, device name "Handi EPN V3", line-oriented ASCII
* Power ............ Motor shields 6 V (XL4015 buck), ESP32 12 V regulated DC

Anatomical naming follows the HANDi Hand assembly manual:
    D1 = thumb, D2 = index, D3 = middle, D4 = ring, D5 = pinky
    D0 = thumb rotation, D1A = thumb adduction (optional Add.able thumb)
    Joint suffixes: P = proximal, I = intermediate, D = distal
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping

# ═════════════════════════════════════════════════════════════════════════════
# Enumerations
# ═════════════════════════════════════════════════════════════════════════════


class Handedness(str, Enum):
    """Which physical hand is mounted / simulated."""

    RIGHT = "right"
    LEFT = "left"


class Digit(str, Enum):
    """Digit numbering per the HANDi Hand assembly manual (Figure 1)."""

    D1_THUMB = "D1"
    D2_INDEX = "D2"
    D3_MIDDLE = "D3"
    D4_RING = "D4"
    D5_PINKY = "D5"


class JointType(str, Enum):
    """Joint indicator per the assembly manual (Figure 2)."""

    ROTATION = "R"      # D0 - thumb rotation / opposition (CMC)
    PROXIMAL = "P"      # MCP
    INTERMEDIATE = "I"  # PIP
    DISTAL = "D"        # DIP / IP


class Actuator(str, Enum):
    """The six position-controlled channels exposed by the firmware.

    The letter IS the serial command prefix.  ``A320`` moves the pinky to
    encoder position 320.
    """

    A_PINKY = "A"
    B_RING = "B"
    C_MIDDLE = "C"
    D_INDEX = "D"
    E_THUMB_LOWER = "E"   # thumb rotation / opposition (MG90S servo)
    F_THUMB_UPPER = "F"   # thumb flexion


class ControlCommand(str, Enum):
    """Single-letter commands that carry no position argument.

    NOTE ON AMBIGUITY: ``C`` alone closes the whole hand, while ``C<position>``
    addresses the middle finger.  The parser therefore resolves ``C`` by looking
    for a numeric suffix.  See :func:`app.domain.protocol.parse_serial_command`.
    """

    OPEN = "O"
    CLOSE = "C"
    PINCH = "P"
    SPIDERMAN = "R"
    PARTIAL_CLAW = "W"
    OK = "Y"
    THUMBS_UP = "L"
    CALL_ME = "M"
    NUMBER_THREE = "H"
    NUMBER_FOUR = "U"
    POINT = "G"
    STOP = "S"
    CALIBRATE = "X"
    INIT_SHIELDS = "I"


class SafetyClass(str, Enum):
    """How a command is treated by the safety validator."""

    MOTION = "motion"        # moves actuators, subject to full range checks
    GESTURE = "gesture"      # firmware-side preset pose
    SYSTEM = "system"        # S / X / I - never blocked, never combined
    EMERGENCY = "emergency"  # S - always permitted, highest priority


# ═════════════════════════════════════════════════════════════════════════════
# Joints (kinematic model used by the 3D simulator)
# ═════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Joint:
    """One rotational degree of freedom in the kinematic chain.

    ``max_flexion_deg`` is the anatomical/mechanical hard stop.  ``coupling`` is
    the fraction of the driving actuator's normalised travel that this joint
    absorbs - the HANDi fingers are tendon driven, so a single motor flexes the
    whole chain with a fixed ratio.
    """

    id: str
    digit: Digit
    joint_type: JointType
    driven_by: Actuator
    min_flexion_deg: float
    max_flexion_deg: float
    coupling: float
    has_potentiometer: bool = True
    axis: str = "x"  # rotation axis in the simulator's local joint frame

    @property
    def range_deg(self) -> float:
        return self.max_flexion_deg - self.min_flexion_deg


#: Full kinematic chain.  11 of these carry a potentiometer, matching the
#: 11 rotary sensors wired to multiplexer channels C5..C15.
JOINTS: Final[tuple[Joint, ...]] = (
    # ── Thumb (D1) ──────────────────────────────────────────────────────────
    Joint("D0",   Digit.D1_THUMB,  JointType.ROTATION,     Actuator.E_THUMB_LOWER, 0.0, 60.0, 1.00, True,  axis="y"),
    Joint("D1_P", Digit.D1_THUMB,  JointType.PROXIMAL,     Actuator.F_THUMB_UPPER, 0.0, 55.0, 1.00, True),
    Joint("D1_D", Digit.D1_THUMB,  JointType.DISTAL,       Actuator.F_THUMB_UPPER, 0.0, 80.0, 0.85, True),
    # ── Index (D2) ──────────────────────────────────────────────────────────
    Joint("D2_P", Digit.D2_INDEX,  JointType.PROXIMAL,     Actuator.D_INDEX,       0.0, 90.0, 1.00, True),
    Joint("D2_I", Digit.D2_INDEX,  JointType.INTERMEDIATE, Actuator.D_INDEX,       0.0, 100.0, 0.95, True),
    Joint("D2_D", Digit.D2_INDEX,  JointType.DISTAL,       Actuator.D_INDEX,       0.0, 70.0, 0.70, False),
    # ── Middle (D3) ─────────────────────────────────────────────────────────
    Joint("D3_P", Digit.D3_MIDDLE, JointType.PROXIMAL,     Actuator.C_MIDDLE,      0.0, 90.0, 1.00, True),
    Joint("D3_I", Digit.D3_MIDDLE, JointType.INTERMEDIATE, Actuator.C_MIDDLE,      0.0, 100.0, 0.95, True),
    Joint("D3_D", Digit.D3_MIDDLE, JointType.DISTAL,       Actuator.C_MIDDLE,      0.0, 70.0, 0.70, False),
    # ── Ring (D4) ───────────────────────────────────────────────────────────
    Joint("D4_P", Digit.D4_RING,   JointType.PROXIMAL,     Actuator.B_RING,        0.0, 90.0, 1.00, True),
    Joint("D4_I", Digit.D4_RING,   JointType.INTERMEDIATE, Actuator.B_RING,        0.0, 100.0, 0.95, True),
    Joint("D4_D", Digit.D4_RING,   JointType.DISTAL,       Actuator.B_RING,        0.0, 70.0, 0.70, False),
    # ── Pinky (D5) ──────────────────────────────────────────────────────────
    Joint("D5_P", Digit.D5_PINKY,  JointType.PROXIMAL,     Actuator.A_PINKY,       0.0, 90.0, 1.00, True),
    Joint("D5_I", Digit.D5_PINKY,  JointType.INTERMEDIATE, Actuator.A_PINKY,       0.0, 100.0, 0.95, True),
    Joint("D5_D", Digit.D5_PINKY,  JointType.DISTAL,       Actuator.A_PINKY,       0.0, 70.0, 0.70, False),
)

JOINTS_BY_ID: Final[Mapping[str, Joint]] = {j.id: j for j in JOINTS}

#: Number of independently commanded degrees of freedom.
DRIVEN_DOF: Final[int] = len(Actuator)
#: Number of modelled rotational joints in the kinematic chain.
KINEMATIC_DOF: Final[int] = len(JOINTS)
#: Rotary potentiometers physically present (multiplexer channels C5..C15).
POTENTIOMETER_COUNT: Final[int] = sum(1 for j in JOINTS if j.has_potentiometer)
#: Force sensitive resistors, one per fingertip.
FSR_COUNT: Final[int] = 5


# ═════════════════════════════════════════════════════════════════════════════
# Actuators
# ═════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ActuatorSpec:
    """Static description of one commandable channel."""

    actuator: Actuator
    label: str
    digit: Digit
    description: str
    hardware: str
    motor_shield_terminal: str
    joints: tuple[str, ...]

    @property
    def letter(self) -> str:
        return self.actuator.value


ACTUATORS: Final[Mapping[Actuator, ActuatorSpec]] = {
    Actuator.A_PINKY: ActuatorSpec(
        Actuator.A_PINKY, "pinky", Digit.D5_PINKY,
        "Flexes/extends the little finger (D5).",
        "Pololu 380:1 HPCB 6V + magnetic encoder", "Shield 1 / M1",
        ("D5_P", "D5_I", "D5_D"),
    ),
    Actuator.B_RING: ActuatorSpec(
        Actuator.B_RING, "ring", Digit.D4_RING,
        "Flexes/extends the ring finger (D4).",
        "Pololu 380:1 HPCB 6V + magnetic encoder", "Shield 2 / M3",
        ("D4_P", "D4_I", "D4_D"),
    ),
    Actuator.C_MIDDLE: ActuatorSpec(
        Actuator.C_MIDDLE, "middle", Digit.D3_MIDDLE,
        "Flexes/extends the middle finger (D3).",
        "Pololu 380:1 HPCB 6V + magnetic encoder", "Shield 2 / M2",
        ("D3_P", "D3_I", "D3_D"),
    ),
    Actuator.D_INDEX: ActuatorSpec(
        Actuator.D_INDEX, "index", Digit.D2_INDEX,
        "Flexes/extends the index finger (D2).",
        "Pololu 380:1 HPCB 6V + magnetic encoder", "Shield 1 / M2",
        ("D2_P", "D2_I", "D2_D"),
    ),
    Actuator.E_THUMB_LOWER: ActuatorSpec(
        Actuator.E_THUMB_LOWER, "thumb_lower", Digit.D1_THUMB,
        "Rotates/opposes the lower thumb segment (D0 rotation).",
        "MG90S metal-gear micro servo", "Servo header (SV1)",
        ("D0",),
    ),
    Actuator.F_THUMB_UPPER: ActuatorSpec(
        Actuator.F_THUMB_UPPER, "thumb_upper", Digit.D1_THUMB,
        "Flexes/extends the upper thumb segment (D1 proximal + distal).",
        "Pololu 380:1 HPCB 6V + magnetic encoder", "Shield 2 / M1",
        ("D1_P", "D1_D"),
    ),
}

JOINTS_BY_ACTUATOR: Final[Mapping[Actuator, tuple[Joint, ...]]] = {
    a: tuple(JOINTS_BY_ID[jid] for jid in spec.joints) for a, spec in ACTUATORS.items()
}


# ═════════════════════════════════════════════════════════════════════════════
# Position limit profiles (versioned - the manuals disagree)
# ═════════════════════════════════════════════════════════════════════════════


class LimitProfileId(str, Enum):
    """Selectable travel-limit profiles.

    The manual states two different sets of position ranges.  Rather than pick
    one silently we version them, so an experiment can declare which envelope it
    was run under and results stay comparable.
    """

    TABLE_5_V3 = "TABLE_5_V3"        # Manual Handi EPN V3, Tabla 5 (body text)
    ANNEX_A_V3 = "ANNEX_A_V3"        # Manual Handi EPN V3, Anexo A (glossary)
    INTERSECTION = "INTERSECTION"    # min() of both - most conservative


@dataclass(frozen=True, slots=True)
class LimitProfile:
    """A complete set of per-actuator encoder travel limits."""

    id: LimitProfileId
    label: str
    source: str
    notes: str
    limits: Mapping[Actuator, tuple[int, int]]

    def bounds(self, actuator: Actuator) -> tuple[int, int]:
        return self.limits[actuator]

    def contains(self, actuator: Actuator, position: int) -> bool:
        lo, hi = self.limits[actuator]
        return lo <= position <= hi

    def clamp(self, actuator: Actuator, position: int) -> int:
        lo, hi = self.limits[actuator]
        return max(lo, min(hi, position))

    def normalise(self, actuator: Actuator, position: int) -> float:
        """Map an encoder position onto 0.0 (extended) .. 1.0 (fully flexed)."""
        lo, hi = self.limits[actuator]
        if hi == lo:
            return 0.0
        return (max(lo, min(hi, position)) - lo) / (hi - lo)


_TABLE_5: Final[dict[Actuator, tuple[int, int]]] = {
    Actuator.A_PINKY: (0, 600),
    Actuator.B_RING: (0, 550),
    Actuator.C_MIDDLE: (0, 600),
    Actuator.D_INDEX: (0, 550),
    Actuator.E_THUMB_LOWER: (0, 130),
    Actuator.F_THUMB_UPPER: (0, 400),
}

_ANNEX_A: Final[dict[Actuator, tuple[int, int]]] = {
    Actuator.A_PINKY: (0, 350),
    Actuator.B_RING: (0, 350),
    Actuator.C_MIDDLE: (0, 440),
    Actuator.D_INDEX: (0, 350),
    Actuator.E_THUMB_LOWER: (0, 120),
    Actuator.F_THUMB_UPPER: (0, 100),
}

_INTERSECTION: Final[dict[Actuator, tuple[int, int]]] = {
    a: (max(_TABLE_5[a][0], _ANNEX_A[a][0]), min(_TABLE_5[a][1], _ANNEX_A[a][1]))
    for a in Actuator
}

LIMIT_PROFILES: Final[Mapping[LimitProfileId, LimitProfile]] = {
    LimitProfileId.TABLE_5_V3: LimitProfile(
        LimitProfileId.TABLE_5_V3,
        "Manual V3 - Tabla 5 (movimientos individuales)",
        "Manual Handi_EPN_V3_ES.pdf, section 'Movimientos basicos', Tabla 5",
        "Default profile. Widest envelope; matches the firmware constants of "
        "Handi_EPN_V3.ino as documented in the body of the manual.",
        _TABLE_5,
    ),
    LimitProfileId.ANNEX_A_V3: LimitProfile(
        LimitProfileId.ANNEX_A_V3,
        "Manual V3 - Anexo A (glosario de comandos)",
        "Manual Handi_EPN_V3_ES.pdf, 'Anexo A - Glosario de comandos', Tabla 8",
        "Conservative envelope published in the command glossary. Disagrees with "
        "Tabla 5; retained for comparison and for mechanically worn units.",
        _ANNEX_A,
    ),
    LimitProfileId.INTERSECTION: LimitProfile(
        LimitProfileId.INTERSECTION,
        "Interseccion estricta (Tabla 5 AND Anexo A)",
        "Derived: element-wise intersection of both documented envelopes.",
        "Hard-safety profile. Guaranteed valid under either reading of the manual.",
        _INTERSECTION,
    ),
}

DEFAULT_LIMIT_PROFILE: Final[LimitProfileId] = LimitProfileId.TABLE_5_V3


def get_limit_profile(profile_id: LimitProfileId | str | None = None) -> LimitProfile:
    """Resolve a limit profile, falling back to the project default."""
    if profile_id is None:
        return LIMIT_PROFILES[DEFAULT_LIMIT_PROFILE]
    if isinstance(profile_id, str):
        try:
            profile_id = LimitProfileId(profile_id)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"Unknown limit profile {profile_id!r}. "
                f"Valid: {[p.value for p in LimitProfileId]}"
            ) from exc
    return LIMIT_PROFILES[profile_id]


# ═════════════════════════════════════════════════════════════════════════════
# Preset gestures (firmware-resident)
# ═════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class GestureSpec:
    """A single-letter preset pose implemented inside the ESP32 firmware."""

    command: ControlCommand
    name: str
    description: str
    safety_class: SafetyClass = SafetyClass.GESTURE
    #: Normalised target flexion (0.0 extended .. 1.0 flexed) per actuator, used
    #: by the 3D simulator to render firmware presets.  ``None`` = not a pose.
    pose: Mapping[Actuator, float] | None = None
    typical_duration_ms: int = 900


def _pose(a: float, b: float, c: float, d: float, e: float, f: float) -> dict[Actuator, float]:
    return {
        Actuator.A_PINKY: a,
        Actuator.B_RING: b,
        Actuator.C_MIDDLE: c,
        Actuator.D_INDEX: d,
        Actuator.E_THUMB_LOWER: e,
        Actuator.F_THUMB_UPPER: f,
    }


GESTURES: Final[Mapping[ControlCommand, GestureSpec]] = {
    ControlCommand.OPEN: GestureSpec(
        ControlCommand.OPEN, "OPEN", "Opens every finger (rest / neutral pose).",
        pose=_pose(0.0, 0.0, 0.0, 0.0, 0.0, 0.0), typical_duration_ms=800,
    ),
    ControlCommand.CLOSE: GestureSpec(
        ControlCommand.CLOSE, "CLOSE", "Closes every finger into a full fist.",
        pose=_pose(1.0, 1.0, 1.0, 1.0, 1.0, 1.0), typical_duration_ms=900,
    ),
    ControlCommand.PINCH: GestureSpec(
        ControlCommand.PINCH, "PINCH", "Pinch: middle finger and thumb flexed to meet.",
        pose=_pose(0.15, 0.15, 0.85, 0.15, 0.90, 0.80), typical_duration_ms=850,
    ),
    ControlCommand.SPIDERMAN: GestureSpec(
        ControlCommand.SPIDERMAN, "SPIDERMAN", "Spiderman: index and pinky extended, middle and ring flexed.",
        pose=_pose(0.0, 1.0, 1.0, 0.0, 0.0, 0.0), typical_duration_ms=900,
    ),
    ControlCommand.PARTIAL_CLAW: GestureSpec(
        ControlCommand.PARTIAL_CLAW, "PARTIAL_CLAW", "Partial claw: index and ring closed, remaining digits open.",
        pose=_pose(0.0, 1.0, 0.0, 1.0, 0.0, 0.0), typical_duration_ms=900,
    ),
    ControlCommand.OK: GestureSpec(
        ControlCommand.OK, "OK", "OK sign: thumb and index form a ring, other fingers extended.",
        pose=_pose(0.1, 0.1, 0.1, 0.85, 0.85, 0.75), typical_duration_ms=900,
    ),
    ControlCommand.THUMBS_UP: GestureSpec(
        ControlCommand.THUMBS_UP, "THUMBS_UP", "Thumbs up: all fingers closed, thumb fully extended.",
        pose=_pose(1.0, 1.0, 1.0, 1.0, 0.0, 0.0), typical_duration_ms=900,
    ),
    ControlCommand.CALL_ME: GestureSpec(
        ControlCommand.CALL_ME, "CALL_ME", "Call-me / shaka: thumb and pinky extended, others closed.",
        pose=_pose(0.0, 1.0, 1.0, 1.0, 0.0, 0.0), typical_duration_ms=900,
    ),
    ControlCommand.NUMBER_THREE: GestureSpec(
        ControlCommand.NUMBER_THREE, "NUMBER_THREE", "Number three: index, middle and ring extended; thumb and pinky closed.",
        pose=_pose(1.0, 0.0, 0.0, 0.0, 1.0, 1.0), typical_duration_ms=900,
    ),
    ControlCommand.NUMBER_FOUR: GestureSpec(
        ControlCommand.NUMBER_FOUR, "NUMBER_FOUR", "Number four: four fingers extended, thumb closed across the palm.",
        pose=_pose(0.0, 0.0, 0.0, 0.0, 1.0, 1.0), typical_duration_ms=900,
    ),
    ControlCommand.POINT: GestureSpec(
        ControlCommand.POINT, "POINT", "Pointing: index extended with the thumb open, other fingers closed.",
        pose=_pose(1.0, 1.0, 1.0, 0.0, 0.0, 0.0), typical_duration_ms=850,
    ),
    ControlCommand.STOP: GestureSpec(
        ControlCommand.STOP, "STOP", "Immediately de-energises all motors. Emergency stop.",
        safety_class=SafetyClass.EMERGENCY, pose=None, typical_duration_ms=0,
    ),
    ControlCommand.CALIBRATE: GestureSpec(
        ControlCommand.CALIBRATE, "CALIBRATE", "Latches the current pose as the encoder zero reference.",
        safety_class=SafetyClass.SYSTEM, pose=None, typical_duration_ms=0,
    ),
    ControlCommand.INIT_SHIELDS: GestureSpec(
        ControlCommand.INIT_SHIELDS, "INIT_SHIELDS", "Re-initialises both Adafruit Motor Shields after a fault.",
        safety_class=SafetyClass.SYSTEM, pose=None, typical_duration_ms=0,
    ),
}

#: Gestures that produce a physical pose the simulator can render.
POSE_GESTURES: Final[tuple[ControlCommand, ...]] = tuple(
    c for c, g in GESTURES.items() if g.pose is not None
)
#: Commands that must never be combined with anything else in one transmission.
EXCLUSIVE_COMMANDS: Final[frozenset[ControlCommand]] = frozenset(
    {ControlCommand.STOP, ControlCommand.CALIBRATE, ControlCommand.INIT_SHIELDS}
)


# ═════════════════════════════════════════════════════════════════════════════
# Motion & safety constants
# ═════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class SafetyLimits:
    """Operational envelope enforced by the validation pipeline."""

    max_simultaneous_actuators: int = 6
    min_speed_pct: int = 5
    max_speed_pct: int = 100
    default_speed_pct: int = 60
    #: Encoder counts per second at 100 % duty, measured on the 380:1 gearmotors.
    max_counts_per_second: int = 900
    min_move_duration_ms: int = 120
    max_move_duration_ms: int = 5_000
    #: Minimum command interval accepted by the firmware's serial loop.
    min_command_interval_ms: int = 50
    #: Fingertip FSR reading above which a grasp is considered force-saturated.
    fsr_saturation_threshold: float = 0.92
    #: Sessions must terminate in the OPEN pose (manual, "Recomendaciones").
    require_open_on_session_end: bool = True


SAFETY: Final[SafetyLimits] = SafetyLimits()


@dataclass(frozen=True, slots=True)
class CommunicationProtocol:
    """Bluetooth SPP link parameters (Manual V3, 'Conexion Bluetooth')."""

    transport: str = "Bluetooth SPP (Serial Port Profile)"
    device_name: str = "Handi EPN V3"
    baud_rate: int = 115_200
    encoding: str = "ASCII"
    terminator: str = "\n"
    separator: str = ","
    max_line_length: int = 128
    case_sensitive: bool = True


PROTOCOL: Final[CommunicationProtocol] = CommunicationProtocol()


# ═════════════════════════════════════════════════════════════════════════════
# EMG acquisition
# ═════════════════════════════════════════════════════════════════════════════

#: Number of surface EMG channels presented to the model.
EMG_CHANNEL_COUNT: Final[int] = 8

#: Canonical channel labels.  Anatomical placement follows a standard
#: transradial 8-site ring montage used for myoelectric prosthesis control.
EMG_CHANNELS: Final[tuple[str, ...]] = tuple(f"CH{i}" for i in range(1, EMG_CHANNEL_COUNT + 1))

EMG_CHANNEL_SITES: Final[Mapping[str, str]] = {
    "CH1": "Flexor digitorum superficialis (volar, medial)",
    "CH2": "Flexor carpi radialis (volar, radial)",
    "CH3": "Flexor carpi ulnaris (volar, ulnar)",
    "CH4": "Palmaris longus (volar, central)",
    "CH5": "Extensor digitorum communis (dorsal, central)",
    "CH6": "Extensor carpi radialis longus (dorsal, radial)",
    "CH7": "Extensor carpi ulnaris (dorsal, ulnar)",
    "CH8": "Brachioradialis (proximal, radial)",
}

#: The stimulus is a raw matrix, not a feature vector: N rows (time steps) by
#: 8 columns (electrodes), amplitudes normalised to [-1.0, 1.0].
EMG_MATRIX_LAYOUT: Final[str] = "rows = time steps (ascending), columns = CH1..CH8"
EMG_AMPLITUDE_MIN: Final[float] = -1.0
EMG_AMPLITUDE_MAX: Final[float] = 1.0

#: Descriptors the backend derives from the matrix and prints alongside it.
EMG_FEATURES: Final[tuple[str, ...]] = (
    "rms", "mav", "zc", "ssc", "wl", "min", "max", "variance",
)

EMG_FEATURE_DOC: Final[Mapping[str, str]] = {
    "rms": "Root mean square amplitude over the window; tracks contraction force.",
    "mav": "Mean absolute value; a cheaper, less noise-sensitive amplitude estimate.",
    "zc": "Zero crossings above a 0.01 deadband; proxy for mean frequency.",
    "ssc": "Slope sign changes above a 0.01 deadband; frequency content.",
    "wl": "Waveform length per sample; combines amplitude and frequency.",
    "min": "Most negative amplitude in the window.",
    "max": "Most positive amplitude in the window.",
    "variance": "Signal variance; scales with motor unit recruitment.",
}

DEFAULT_EMG_SAMPLE_RATE_HZ: Final[int] = 1_000
DEFAULT_EMG_SAMPLES: Final[int] = 200
