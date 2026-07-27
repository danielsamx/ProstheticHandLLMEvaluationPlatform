"""Block 2 of 3 - the Technical Context.

A structured *summary* of the four technical manuals, not a transcription.  It
is generated from :mod:`app.domain` so the text the model reads can never drift
from the validators the response is checked against - if an engineer changes a
limit in ``hand_spec.py``, the prompt changes with it.

The generated text is the factory default.  The active context lives in
``technical_context_versions`` and is fully editable from the UI, so a
researcher can A/B a hand-written context against the generated one.
"""

from __future__ import annotations

import json
from typing import Final

from app.domain.hand_spec import (
    ACTUATORS,
    DEFAULT_EMG_SAMPLE_RATE_HZ,
    DEFAULT_EMG_SAMPLES,
    EMG_AMPLITUDE_MAX,
    EMG_AMPLITUDE_MIN,
    EMG_CHANNEL_COUNT,
    EMG_MATRIX_LAYOUT,
    DRIVEN_DOF,
    EMG_CHANNEL_SITES,
    EMG_FEATURE_DOC,
    FSR_COUNT,
    GESTURES,
    KINEMATIC_DOF,
    POTENTIOMETER_COUNT,
    PROTOCOL,
    SAFETY,
    Actuator,
    ControlCommand,
    LimitProfile,
    SafetyClass,
    get_limit_profile,
)
from app.domain.kinematics import describe_kinematics
from app.schemas.llm_output import llm_json_schema

#: Bumped to 2.0.0: the EMG section now describes a raw sample matrix
#: rather than eight scalar feature vectors.
TECHNICAL_CONTEXT_VERSION: Final[str] = "2.0.0"
TECHNICAL_CONTEXT_NAME: Final[str] = "HANDi EPN V3 - generated from manuals"


def _limits_table(profile: LimitProfile) -> str:
    header = (
        "| Cmd | Digit | Actuator          | Min | Max | Hardware                    |\n"
        "|-----|-------|-------------------|-----|-----|-----------------------------|"
    )
    rows = []
    for actuator, spec in ACTUATORS.items():
        lo, hi = profile.bounds(actuator)
        rows.append(
            f"| {actuator.value}   | {spec.digit.value:<5} | {spec.label:<17} "
            f"| {lo:<3} | {hi:<3} | {spec.hardware[:27]:<27} |"
        )
    return "\n".join([header, *rows])


def _gesture_table() -> str:
    header = "| Cmd | Name          | Class     | Description |\n|-----|---------------|-----------|-------------|"
    rows = []
    for command, gesture in GESTURES.items():
        rows.append(
            f"| {command.value}   | {gesture.name:<13} | "
            f"{gesture.safety_class.value:<9} | {gesture.description} |"
        )
    return "\n".join([header, *rows])


def _emg_block() -> str:
    sites = "\n".join(f"  {ch}: {site}" for ch, site in EMG_CHANNEL_SITES.items())
    feats = "\n".join(f"  {k}: {v}" for k, v in EMG_FEATURE_DOC.items())
    return (
        f"INPUT FORMAT: you receive a raw sample MATRIX, not a summary.\n"
        f"  Shape: N x {EMG_CHANNEL_COUNT}\n"
        f"  Layout: {EMG_MATRIX_LAYOUT}\n"
        f"  Amplitude range: {EMG_AMPLITUDE_MIN} to {EMG_AMPLITUDE_MAX} (normalised)\n"
        f"  Typical window: {DEFAULT_EMG_SAMPLES} rows at "
        f"{DEFAULT_EMG_SAMPLE_RATE_HZ} Hz\n"
        f"  Each row is one instant in time; read DOWN a column to follow one\n"
        f"  electrode through the window.\n\n"
        f"Electrode montage (columns, left to right):\n{sites}\n\n"
        f"A derived feature table is supplied beneath the matrix. It is computed\n"
        f"from the COMPLETE window even when the printed matrix is decimated, so\n"
        f"trust the table for magnitudes and the matrix for temporal structure:\n"
        f"{feats}"
    )


def build_technical_context(
    profile: LimitProfile | None = None,
    *,
    include_json_schema: bool = True,
) -> str:
    """Render the technical context block for a given limit profile."""
    profile = profile or get_limit_profile()

    pose_gestures = ", ".join(
        g.command.value for g in GESTURES.values() if g.safety_class is SafetyClass.GESTURE
    )
    system_gestures = ", ".join(
        g.command.value for g in GESTURES.values()
        if g.safety_class in (SafetyClass.SYSTEM, SafetyClass.EMERGENCY)
    )

    schema_block = ""
    if include_json_schema:
        schema_block = (
            "\n## 9. OUTPUT JSON SCHEMA (authoritative)\n\n"
            "Your response is validated against this JSON Schema. Any deviation "
            "marks the execution as failed.\n\n"
            "```json\n" + json.dumps(llm_json_schema(), indent=2, ensure_ascii=False) + "\n```\n"
        )

    return f"""\
# TECHNICAL CONTEXT - HANDi EPN V3 PROSTHETIC HAND

Active mechanical limit profile: **{profile.id.value}** ({profile.label})
Source: {profile.source}

## 1. MECHANICAL ARCHITECTURE

Anthropomorphic 3D-printed hand, tendon driven, developed at Escuela Politecnica
Nacional (Laboratorio "Alan Turing") on the open-source HANDi Hand platform.

- Independently commanded degrees of freedom: {DRIVEN_DOF}
- Modelled rotational joints in the kinematic chain: {KINEMATIC_DOF}
- Digits: D1 thumb, D2 index, D3 middle, D4 ring, D5 pinky
- Joint indicators: R = rotation (thumb only), P = proximal (MCP),
  I = intermediate (PIP), D = distal (DIP/IP)
- Actuation: 5 x Pololu 380:1 HPCB 6 V gearmotors with 12 CPR magnetic encoders,
  plus 1 x MG90S servo for thumb rotation
- Controller: ESP32 (Wemos D1 R32) stacked with 2 x Adafruit Motor Shield V3
- Proprioception: {POTENTIOMETER_COUNT} rotary potentiometers (via CD74HC4067 16:1
  multiplexer, channels C5..C15) and {FSR_COUNT} fingertip force-sensitive resistors

CRITICAL COUPLING RULE: each finger is driven by ONE motor through a tendon.
Commanding a finger flexes its whole chain by a fixed ratio. Individual phalanges
are NOT independently addressable.

## 2. COMMAND SET - POSITIONS

Format: `<LETTER><INTEGER>` where INTEGER is an absolute encoder target.
Several may be combined in one line, separated by commas.

{_limits_table(profile)}

Positions outside these bounds are rejected. 0 = fully extended (open),
maximum = fully flexed (closed).

## 3. COMMAND SET - PRESET GESTURES

Format: a single letter with no numeric argument.

{_gesture_table()}

Pose gestures: {pose_gestures}
System commands (must be sent alone): {system_gestures}

DISAMBIGUATION: `C` alone closes the whole hand. `C` followed by digits (e.g.
`C400`) addresses the middle finger. Never emit a bare `C` when you mean the
middle finger.

## 4. KINEMATIC COUPLING (actuator -> joints, max flexion, coupling ratio)

{describe_kinematics()}

## 5. COMMUNICATION PROTOCOL

- Transport: {PROTOCOL.transport}
- Device name: "{PROTOCOL.device_name}"
- Baud rate: {PROTOCOL.baud_rate}
- Encoding: {PROTOCOL.encoding}, case sensitive, uppercase letters only
- Token separator: "{PROTOCOL.separator}"
- Line terminator: newline
- Maximum line length: {PROTOCOL.max_line_length} characters

Valid examples:
    A320,B180,C400,D200      -> four fingers to explicit positions
    E120,F350                -> thumb rotation and flexion
    P                        -> firmware pinch preset
    S                        -> emergency stop

Invalid examples:
    A700                     -> exceeds the documented maximum
    P,A320                   -> preset gesture combined with positions
    a320                     -> lowercase
    A320;B180                -> wrong separator
    Z100                     -> command letter does not exist

## 6. MECHANICAL AND SAFETY CONSTRAINTS

- Maximum actuators driven simultaneously: {SAFETY.max_simultaneous_actuators}
- Speed envelope: {SAFETY.min_speed_pct}%-{SAFETY.max_speed_pct}%
  (default {SAFETY.default_speed_pct}%)
- Maximum encoder rate at 100% duty: {SAFETY.max_counts_per_second} counts/s
- Movement duration must fall between {SAFETY.min_move_duration_ms} ms and
  {SAFETY.max_move_duration_ms} ms
- Minimum interval between transmissions: {SAFETY.min_command_interval_ms} ms
- Fingertip FSR above {SAFETY.fsr_saturation_threshold:.2f} indicates force
  saturation; do not increase flexion further
- A fully opposed AND fully flexed thumb combined with a fully flexed index or
  middle finger is a collision: avoid it
- The hand must be returned to the OPEN pose at the end of a session

## 7. EMG INPUT

{_emg_block()}

Interpretation guidance:
- Raw EMG is a zero-mean stochastic signal. Its INFORMATION IS IN THE ENVELOPE
  and the frequency content, not in any individual sample. Never read a single
  row as a command.
- Volar/flexor columns (CH1-CH4) dominant  -> closing / grasping intent
- Dorsal/extensor columns (CH5-CH7) dominant -> opening / extension intent
- Simultaneous high flexor AND extensor RMS -> co-contraction, normally a
  deliberate STOP request
- All channels below approximately 0.10 RMS -> rest; return intent="no_action"
- Amplitude gradation encodes movement magnitude, not only movement selection
- A rising envelope across the window indicates an onset; a flat one indicates a
  sustained hold

## 8. RESPONSE DISCIPLINE

Emit one JSON object. No prose. No code fences. All required fields present.
`serial_command` must agree with `intent`, `gesture` and `commands`.
{schema_block}"""


def default_technical_context() -> str:
    return build_technical_context()
