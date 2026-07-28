"""The three frozen blocks, pinned to the wording they were authored with.

Everything numeric in blocks 2 and 3 is generated from :mod:`app.domain`, which
is what stops a prompt promising the model a limit the validators then reject,
or naming a channel as a flexor that the feature extractor counts as an
extensor. The cost of generating them is that an unrelated domain edit can
silently reword the prompt — and because all three frozen blocks are hashed into
``frozen_context_sha256``, a reworded prompt quietly makes every prior execution
incomparable to every subsequent one.

These tests are the tripwire. They do not exist to make the text hard to change;
they exist to make changing it *deliberate*. When one fails, the right response
is usually to update the expected text and bump that block's version constant,
so the seed files a new artefact and the history stays honest about which
wording produced which result.
"""

from __future__ import annotations

from app.domain.hand_spec import LimitProfileId, get_limit_profile
from app.prompts.emg_context import EMG_CONTEXT_VERSION, build_emg_context
from app.prompts.system_prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION
from app.prompts.technical_context import (
    TECHNICAL_CONTEXT_VERSION,
    build_technical_context,
)

AUTHORED_SYSTEM_PROMPT = """\
You are the embedded control layer of the HANDi EPN V3 robotic prosthetic hand.
Infer the user's intended movement from surface EMG.
Return exactly one valid JSON object.
Never output explanations, markdown or extra text.
Always generate the safest valid command.
Respect every hardware constraint.
Identical input must always produce identical output.
"""

AUTHORED_TECHNICAL_CONTEXT = """\
Actuators
A Pinky      0-600
B Ring       0-550
C Middle     0-600
D Index      0-550
E ThumbLow   0-130
F ThumbHigh  0-400
Preset gestures
O OPEN
C CLOSE
P PINCH
R SPIDERMAN
W PARTIAL_CLAW
Y OK
L THUMBS_UP
M CALL_ME
H THREE
U FOUR
G POINT
S STOP
X CALIBRATION
I INITIALIZATION
S, X, I must always be sent alone.
Bluetooth protocol
ASCII
Uppercase
Comma-separated
Examples
P
S
A320,B240,C400
Safety
Never exceed actuator limits.
Never generate impossible poses.
Avoid thumb-index collision.
Maximum 6 actuator commands.
"""

AUTHORED_EMG_CONTEXT = """\
EMG KNOWLEDGE CONTEXT
Surface EMG is acquired from an eight-channel Myo Armband.
Channels
CH1 Flexor Digitorum Superficialis
CH2 Flexor Carpi Radialis
CH3 Flexor Carpi Ulnaris
CH4 Palmaris Longus
CH5 Extensor Digitorum Communis
CH6 Extensor Carpi Radialis Longus
CH7 Extensor Carpi Ulnaris
CH8 Brachioradialis
Interpret the complete activation pattern.
Do not classify movements from a single threshold.
Evaluate jointly
- raw EMG
- RMS
- MAV
- WL
- ZC
- SSC
- spatial distribution
- relative activation
Normal grasping may activate both flexors and extensors because of physiological coactivation.
Simultaneous agonist and antagonist activity alone does not indicate STOP.
Infer the movement whose overall pattern is most consistent with the observed EMG.
If evidence is insufficient return no_action.
Return STOP only when intentional co-contraction is the most probable interpretation.
"""


def _diff(actual: str, expected: str) -> str:
    """The first differing line, which is what a failure needs to point at."""
    for index, (got, want) in enumerate(
        zip(actual.splitlines(), expected.splitlines()), start=1
    ):
        if got != want:
            return f"line {index}\n  generated: {got!r}\n  authored : {want!r}"
    return (
        f"line count: generated {len(actual.splitlines())}, "
        f"authored {len(expected.splitlines())}"
    )


def test_system_prompt_matches_author_text():
    assert SYSTEM_PROMPT == AUTHORED_SYSTEM_PROMPT, _diff(
        SYSTEM_PROMPT, AUTHORED_SYSTEM_PROMPT
    )


def test_technical_context_matches_author_text():
    """Generated from the domain, but must render the authored wording exactly.

    A failure here means a domain constant moved. The prompt is not wrong — it
    is telling the model the truth about the new domain — but the wording has
    changed, so the version constant must move with it.
    """
    generated = build_technical_context(get_limit_profile(LimitProfileId.TABLE_5_V3))
    assert generated == AUTHORED_TECHNICAL_CONTEXT, _diff(
        generated, AUTHORED_TECHNICAL_CONTEXT
    )


def test_emg_context_matches_author_text():
    generated = build_emg_context()
    assert generated == AUTHORED_EMG_CONTEXT, _diff(generated, AUTHORED_EMG_CONTEXT)


def test_the_emg_block_contradicts_the_naive_co_contraction_rule():
    """Worth pinning on its own, because it reverses earlier guidance.

    A previous version told the model that near-equal flexor and extensor
    activity meant STOP. That is wrong physiologically — a normal grasp recruits
    antagonists to stabilise the wrist — so the rule turned ordinary grasping
    into an emergency halt. A model given the simple rule will follow it, so the
    correction has to be explicit rather than merely omitted.
    """
    text = build_emg_context()
    assert "Simultaneous agonist and antagonist activity alone does not indicate STOP." in text
    assert "physiological coactivation" in text
    assert "Do not classify movements from a single threshold." in text


def test_the_blocks_carry_the_versions_this_text_was_filed_under():
    """The seed keys artefacts on (name, version). If the text changes without
    the version moving, the seed silently keeps serving the old row and every
    execution is attributed to wording that was never sent.

    All four blocks ship at 1.0. The numbers previously carried the platform's
    own development history — a system prompt at 6.0.0 before anyone had run an
    experiment — which made the artefact table read as though five earlier
    studies had happened. That history belongs in git.
    """
    assert SYSTEM_PROMPT_VERSION == "1.0"
    assert TECHNICAL_CONTEXT_VERSION == "1.0"
    assert EMG_CONTEXT_VERSION == "1.0"
