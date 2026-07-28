"""Block 2 of 3 - the Technical Context.

A structured *summary* of the four technical manuals, not a transcription.

The wording is author-supplied and deliberately terse. Everything numeric in it
is still generated from :mod:`app.domain`, so the text the model reads cannot
drift from the validators its answer is checked against: change a limit in
``hand_spec.py`` and this block changes with it. A prompt that promises the
model a range the pipeline then rejects is the one failure mode that would make
every result uninterpretable, so no figure here is typed by hand.

``test_technical_context_matches_author_text`` pins the rendered output against
the supplied wording, line for line, under the default profile. If a domain
edit would change the text, that test fails and the change becomes a deliberate
decision instead of a silent one.

The generated text is the factory default. The active context lives in
``technical_context_versions`` and is fully editable from the UI, so a
researcher can A/B a hand-written context against the generated one.
"""

from __future__ import annotations

from typing import Final

from app.domain.hand_spec import (
    ACTUATORS,
    DRIVEN_DOF,
    EMG_CHANNEL_COUNT,
    EMG_CHANNEL_SITES,
    EXCLUSIVE_COMMANDS,
    GESTURES,
    JOINTS_BY_ACTUATOR,
    KINEMATIC_DOF,
    PROTOCOL,
    SAFETY,
    Actuator,
    ControlCommand,
    LimitProfile,
    get_limit_profile,
)
from app.schemas.llm_output import output_contract

#: 2.0.0 - the EMG section describes a raw sample matrix rather than eight
#:         scalar feature vectors.
#: 3.0.0 - the output contract is stated compactly instead of embedding the full
#:         JSON Schema.
#: 4.0.0 - author-supplied wording: telegraphic section headings, no prose, and
#:         the JSON response shape stated inline. Roughly a third the length of
#:         the 3.0.0 text for the same content, which matters directly: the
#:         block is frozen into every prompt, so its size is subtracted from the
#:         context available to the EMG matrix on every single execution.
TECHNICAL_CONTEXT_VERSION: Final[str] = "4.0.0"
TECHNICAL_CONTEXT_NAME: Final[str] = "HANDi EPN V3 - generated from manuals"

#: The firmware's own identifiers are long. In a block this compact the extra
#: characters cost more than the clarity they buy, and the letter is what the
#: model actually emits, so the name only has to be recognisable.
_COMPACT_GESTURE_NAMES: Final[dict[str, str]] = {
    "NUMBER_THREE": "3",
    "NUMBER_FOUR": "4",
    "CALIBRATE": "CAL",
    "INIT_SHIELDS": "INIT",
}


def _commands_line(profile: LimitProfile) -> str:
    """`A(pinky 0-600), B(ring 0-550), ...` for the active limit profile."""
    parts = []
    for actuator, spec in ACTUATORS.items():
        low, high = profile.bounds(actuator)
        parts.append(f"{actuator.value}({spec.label} {low}-{high})")
    return ", ".join(parts)


def _gestures_line() -> str:
    return ", ".join(
        f"{command.value}={_COMPACT_GESTURE_NAMES.get(gesture.name, gesture.name)}"
        for command, gesture in GESTURES.items()
    )


def _coupling_block() -> str:
    """One line per distinct coupling, actuators sharing a signature merged.

    The four long fingers are mechanically identical, so listing them
    separately would repeat the same three joints four times over. The grouping
    is computed from the couplings rather than assumed, so if a finger is ever
    given its own geometry it will split onto its own line by itself.
    """
    signatures: dict[str, list[str]] = {}
    for actuator in Actuator:
        signature = ", ".join(
            f"{joint.joint_type.value}({joint.min_flexion_deg:.0f}-"
            f"{joint.max_flexion_deg:.0f}°×{joint.coupling:.2f})"
            for joint in JOINTS_BY_ACTUATOR[actuator]
        )
        signatures.setdefault(signature, []).append(actuator.value)

    return "\n".join(
        f"{'/'.join(letters)}: {signature}"
        for signature, letters in signatures.items()
    )


def _emg_channel_line() -> str:
    """`CH1=Flexor_digitorum_superficialis, ...` — muscle only, no location.

    The anatomical location in ``EMG_CHANNEL_SITES`` is for the researcher
    placing electrodes; the model only needs to know which muscle a column
    belongs to in order to group flexors against extensors.
    """
    parts = []
    for channel, site in EMG_CHANNEL_SITES.items():
        muscle = site.split(" (")[0].replace(" ", "_")
        parts.append(f"{channel}={muscle}")
    return ", ".join(parts) + "."


def build_technical_context(
    profile: LimitProfile | None = None,
    *,
    include_json_schema: bool = True,
) -> str:
    """Render the technical context block for a given limit profile."""
    profile = profile or get_limit_profile()

    # Ordered by the gesture table above rather than by set iteration order, so
    # the two lists read consistently and the text is stable between runs —
    # a set's order is not guaranteed, and an unstable prompt would change the
    # frozen-context hash for no reason and break comparability across sessions.
    exclusive = ",".join(
        command.value for command in GESTURES if command in EXCLUSIVE_COMMANDS
    )
    close = ControlCommand.CLOSE.value
    middle = Actuator.C_MIDDLE.value

    return f"""\
MECHANICS
{DRIVEN_DOF} DOF, {KINEMATIC_DOF} joints. One motor per finger (A-F). D1=thumb, D2=index, D3=middle, D4=ring, D5=pinky.
No individual phalanges.
COMMANDS (0=open, max=closed)
{_commands_line(profile)}
GESTURES (single letter, no args)
{_gestures_line()}
System: {exclusive} alone. Bare {close}=CLOSE, {middle}400=middle finger.
COUPLING
{_coupling_block()}
PROTOCOL
Bluetooth SPP {PROTOCOL.baud_rate} baud, {PROTOCOL.encoding} uppercase, comma-separated, newline, max {PROTOCOL.max_line_length} chars.
Valid: A320,B180,C400,D200 | E120,F350 | P | S
SAFETY
Max {SAFETY.max_simultaneous_actuators} actuators. Speed {SAFETY.min_speed_pct}-{SAFETY.max_speed_pct}% (default {SAFETY.default_speed_pct}). Duration {SAFETY.min_move_duration_ms}-{SAFETY.max_move_duration_ms}ms. Min {SAFETY.min_command_interval_ms}ms between transmissions.
Avoid: fully flexed thumb + fully flexed index/middle (collision).
Return to OPEN at session end.
EMG INPUT
Matrix N×{EMG_CHANNEL_COUNT} (int8 signed -128..127). {_emg_channel_line()}
Read relatively, not absolute.
flexor_ratio = flexor RMS / (flexor RMS + extensor RMS)
- >0.65 → closing/grasping
- <0.35 → opening/extension
- ~0.5 with both strong → co-contraction = STOP
- all channels near floor → rest/no_action
{output_contract()}"""


def default_technical_context() -> str:
    return build_technical_context()
