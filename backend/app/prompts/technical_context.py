"""Block 2 of 4 - the Technical Context.

What the hand *is*: actuators and their ranges, the gestures the firmware
implements, the syntax of a command, the safety envelope. Nothing about EMG —
that moved to block 3 when it became its own artefact.

Nothing about the transport either. The block used to open its format section
with "Bluetooth protocol / ASCII", which told the model about a link it has no
part in: it does not open the socket, choose the baud rate or see the wire. What
it needs is the *syntax* — uppercase letters, comma-separated — and that is what
remains. Transport belongs to `app.domain.protocol` and to the browser's serial
link, and mentioning it here only spent context on a fact the model cannot act
on.

The split is not cosmetic. "What can this hand do?" is a fact about hardware
that changes only when the hardware does; "how should EMG be interpreted?" is a
methodological position that a researcher will want to revise repeatedly. Kept
in one block, every experiment on the second question would also reversion the
first, and the two would be impossible to attribute apart.

The wording is author-supplied and deliberately terse. Everything numeric is
still generated from :mod:`app.domain`, so the text the model reads cannot drift
from the validators its answer is checked against: change a limit in
``hand_spec.py`` and this block changes with it. A prompt that promises the
model a range the pipeline then rejects is the one failure mode that would make
every result uninterpretable, so no figure here is typed by hand.

``test_technical_context_matches_author_text`` pins the rendered output against
the supplied wording, line for line. If a domain edit would change the text,
that test fails and the change becomes deliberate instead of silent.
"""

from __future__ import annotations

from typing import Final

from app.domain.hand_spec import (
    ACTUATORS,
    EXCLUSIVE_COMMANDS,
    GESTURES,
    SAFETY,
    Actuator,
    LimitProfile,
    get_limit_profile,
)

#: Every block starts at 1.0.
#:
#: The numbers used to carry the platform's own development history — a system
#: prompt at 6.0.0 before anyone had run an experiment, because it had been
#: rewritten six times while the code was being built. That history is in git,
#: where it belongs; here it only made the artefact table read as though five
#: earlier studies had happened.
#:
#: From here the version means what a researcher expects it to mean: 1.0 is the
#: text this platform ships with, and anything above it is a change someone
#: made deliberately and can be asked about.
TECHNICAL_CONTEXT_VERSION: Final[str] = "1.0"
TECHNICAL_CONTEXT_NAME: Final[str] = "HANDi EPN V3 - multimodal control contract"

#: The reduced variant, for the envelope-image flow.
#:
#: A separate artefact rather than a flag on the full one, because the two are
#: not versions of the same text: they describe different capability sets. An
#: execution run under "the hand can do fourteen gestures and six actuators" is
#: not comparable to one run under "the hand opens and closes", and keeping them
#: distinct means the prompt-configuration table shows two rows instead of
#: hiding the difference inside one.
#:
#: The actuator table is gone from it, not merely unmentioned. If the answer can
#: only be O, C or nothing, then six ranges of positions are context spent on a
#: vocabulary the model is not allowed to use - and worse, an invitation to use
#: it.
#:
#: Two encoder lines went with it: the priority of physical encoders over
#: simulated ones, and the rule that stale telemetry or a possible stall forbids
#: a new movement. Both were true and neither was usable - the prompt carries no
#: telemetry, so the model was being told to weigh evidence it does not receive.
#: That is the same failure as printing a column of zeros for ZC. The rules
#: themselves are not lost: they are enforced by the validation pipeline, on the
#: side that actually has the encoder readings.
TECHNICAL_CONTEXT_OPEN_CLOSE_VERSION: Final[str] = "1.0"
TECHNICAL_CONTEXT_OPEN_CLOSE_NAME: Final[str] = "HANDi EPN V3 - open and close only"

#: The firmware's identifiers, spelled as the author's table spells them.
_GESTURE_NAMES: Final[dict[str, str]] = {
    "NUMBER_THREE": "THREE",
    "NUMBER_FOUR": "FOUR",
    "CALIBRATE": "CALIBRATION",
    "INIT_SHIELDS": "INITIALIZATION",
}

#: Display names for the actuators, in the author's camel-case spelling.
_ACTUATOR_NAMES: Final[dict[str, str]] = {
    "pinky": "Pinky",
    "ring": "Ring",
    "middle": "Middle",
    "index": "Index",
    "thumb_lower": "ThumbLow",
    "thumb_upper": "ThumbHigh",
}


def _actuator_table(profile: LimitProfile) -> str:
    """Aligned so the ranges line up. Numbers from the active limit profile."""
    rows = []
    for actuator, spec in ACTUATORS.items():
        low, high = profile.bounds(actuator)
        label = _ACTUATOR_NAMES.get(spec.label, spec.label)
        rows.append(f"{actuator.value} {label:<11}{low}-{high}")
    return "\n".join(rows)


def _gesture_table() -> str:
    return "\n".join(
        f"{command.value} {_GESTURE_NAMES.get(gesture.name, gesture.name)}"
        for command, gesture in GESTURES.items()
    )


def build_technical_context(
    profile: LimitProfile | None = None,
    *,
    include_json_schema: bool = False,
) -> str:
    """Render the technical context block for a given limit profile.

    ``include_json_schema`` is retained for the stored-artefact API and is now
    a no-op: the response shape reaches the model through `response_format`,
    which constrains decoding rather than merely asking. A second copy in the
    prose could only ever agree or disagree with it, and disagreeing is the
    dangerous outcome.
    """
    profile = profile or get_limit_profile()
    exclusive = ", ".join(
        command.value for command in GESTURES if command in EXCLUSIVE_COMMANDS
    )

    return f"""\
Actuators
{_actuator_table(profile)}
Preset gestures
{_gesture_table()}
{exclusive} must always be sent alone.
Command format
Uppercase letters
Comma-separated
Examples
P
S
A320,B240,C400
Safety
Never exceed actuator limits.
Never generate impossible poses.
Avoid thumb-index collision.
Maximum {SAFETY.max_simultaneous_actuators} actuator commands.
Encoder policy
Physical encoders take priority over simulated encoders.
Do not move farther into an open or closed limit.
Stale telemetry, a possible stall, or opposing motion forbids a new movement.
no_action means no transmission and keeps the current position.
STOP means intent=stop and serial_command=S, only for motion already in progress.
"""


def build_technical_context_open_close() -> str:
    """The hand, described only as far as opening and closing.

    Deliberately short. The whole point of the reduced vocabulary is that the
    model has three possible answers, and a block that spent four hundred tokens
    describing fourteen gestures and six actuator ranges would be teaching a
    vocabulary the validator then rejects — which is the exact failure the
    generated-from-domain rule exists to prevent, arrived at from the other
    direction.

    The gesture letters are still read from :mod:`app.domain`, so if the
    firmware ever renames OPEN or CLOSE this text follows.
    """
    letters = {gesture.name: command.value for command, gesture in GESTURES.items()}
    open_cmd = letters.get("OPEN", "O")
    close_cmd = letters.get("CLOSE", "C")

    return f"""\
Supported commands
{open_cmd} fully open the hand
{close_cmd} fully close the hand
"" do not move
These three are the only permitted answers.
Command format
A single uppercase letter, or the empty string.
Never combine commands.
Never send actuator positions.
Safety
Never generate impossible poses.
{close_cmd} alone means CLOSE. It is never a finger position.
Encoder policy
Do not move farther into an open or closed limit.
"" means no transmission and keeps the current position.
"""


def default_technical_context() -> str:
    return build_technical_context()
