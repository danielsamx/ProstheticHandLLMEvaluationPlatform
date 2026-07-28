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
from app.schemas.llm_output import output_contract

#: 2.0.0 — the EMG section describes a raw sample matrix rather than eight
#:         scalar feature vectors.
#: 3.0.0 — the output contract is stated compactly instead of embedding the full
#:         JSON Schema. The schema is already sent as `response_format`, so
#:         inlining it too spent ~1,300 tokens repeating a constraint the
#:         runtime enforces anyway.
TECHNICAL_CONTEXT_VERSION: Final[str] = "3.0.0"
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
    sites = "\n".join(f"  {ch}  {site}" for ch, site in EMG_CHANNEL_SITES.items())
    return (
        f"Input: a raw sample matrix, N x {EMG_CHANNEL_COUNT}. One row per time "
        f"step (ascending); columns are CH1..CH8 in order. Values are the "
        f"converter's own output, UNSCALED - read them relatively, never against "
        f"an absolute threshold.\n\n"
        f"Electrodes (column order):\n{sites}"
    )


def _output_block() -> str:
    """What to send back. Short, because the contract now is one line."""
    return output_contract()


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

    schema_block = "\n## 9. WHAT TO SEND BACK\n\n" + _output_block() + "\n"

    return f"""\
# HANDi EPN V3 - TECHNICAL CONTEXT

Limit profile: **{profile.id.value}** ({profile.source})

## 1. MECHANICS

3D-printed anthropomorphic hand, tendon driven. {DRIVEN_DOF} commanded DOF,
{KINEMATIC_DOF} modelled joints, {POTENTIOMETER_COUNT} joint potentiometers,
{FSR_COUNT} fingertip force sensors.
Digits: D1 thumb, D2 index, D3 middle, D4 ring, D5 pinky.

COUPLING: one motor drives a whole finger through a tendon. Commanding a finger
flexes its entire chain at a fixed ratio. Individual phalanges are NOT
addressable.

## 2. POSITION COMMANDS

`<LETTER><INTEGER>` - absolute encoder target. Comma-separate to combine.

{_limits_table(profile)}

0 = fully extended (open). Maximum = fully flexed (closed). Out-of-range values
are rejected.

## 3. PRESET GESTURES

Single letter, no argument.

{_gesture_table()}

System commands (send alone): {system_gestures}

DISAMBIGUATION: bare `C` closes the hand; `C` with digits (`C400`) addresses the
middle finger. Never send a bare `C` meaning the middle finger.

## 4. KINEMATIC COUPLING

{describe_kinematics()}

## 5. PROTOCOL

{PROTOCOL.transport}, {PROTOCOL.baud_rate} baud, ASCII uppercase, `,` separated,
newline terminated, max {PROTOCOL.max_line_length} chars.

Valid:   `A320,B180,C400,D200`  ·  `E120,F350`  ·  `P`  ·  `S`
Invalid: `A700` (over range) · `P,A320` (gesture + positions) · `a320` (lower
case) · `A320;B180` (wrong separator) · `Z100` (no such command)

## 6. LIMITS AND SAFETY

Max {SAFETY.max_simultaneous_actuators} actuators at once. Speed
{SAFETY.min_speed_pct}-{SAFETY.max_speed_pct}% (default {SAFETY.default_speed_pct}).
Motion {SAFETY.min_move_duration_ms}-{SAFETY.max_move_duration_ms} ms.
Minimum {SAFETY.min_command_interval_ms} ms between transmissions.

- A fully opposed AND fully flexed thumb against a fully flexed index or middle
  finger is a collision. Avoid it.
- Return the hand to OPEN at the end of a session.

## 7. EMG INPUT

{_emg_block()}

Features supplied below the matrix, computed over the COMPLETE window even when
the printed excerpt is decimated:
  rms/mav = amplitude (force) · zc/ssc = frequency content · wl = both combined

HOW TO READ IT - the decisive quantity is the BALANCE between groups, not any
absolute number. Gain, electrode placement and subject all shift the absolute
scale; the ratio survives all three.

  flexor_ratio = flexor RMS / (flexor RMS + extensor RMS)

  > 0.65        volar group dominates      -> closing / grasping
  < 0.35        dorsal group dominates     -> opening / extension
  ~ 0.5, both groups strong relative to the window's own baseline
                -> co-contraction, normally a deliberate STOP
  all channels near the window's floor     -> rest, return intent="no_action"

Raw EMG is a zero-mean stochastic signal. Its information is in the envelope and
the frequency content. Never read a single row as a command.

## 8. RESPONSE
{schema_block}"""


def default_technical_context() -> str:
    return build_technical_context()
