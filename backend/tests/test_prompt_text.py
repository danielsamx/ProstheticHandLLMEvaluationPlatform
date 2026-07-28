"""The two frozen blocks, pinned to the wording they were authored with.

Every number in the technical context is generated from :mod:`app.domain`, which
is what stops the prompt promising the model a limit the validators then reject.
The cost of generating it is that an unrelated domain edit can silently reword
the prompt — and because the frozen blocks are hashed into
``frozen_context_sha256``, a reworded prompt quietly makes every prior execution
incomparable to every subsequent one.

These tests are the tripwire. They do not exist to make the text hard to change;
they exist to make changing it *deliberate*. When one fails, the right response
is usually to update the expected text and bump the block's version constant, so
the seed files a new artefact and the history stays honest about which wording
produced which result.
"""

from __future__ import annotations

from app.domain.hand_spec import LimitProfileId, get_limit_profile
from app.prompts.system_prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION
from app.prompts.technical_context import (
    TECHNICAL_CONTEXT_VERSION,
    build_technical_context,
)

AUTHORED_SYSTEM_PROMPT = """\
You are HANDi EPN V3 control layer. Deterministic EMG→actuator transducer.
Output: valid JSON only. No prose, markdown or code fences.
Conform to schema. serial_command must match intent/gesture/commands.
HARDWARE:
- Use only listed commands/gestures. Never invent.
- Never exceed position ranges (mechanical stops).
- One motor per finger chain. No individual phalanx.
- Gestures and positions are mutually exclusive. S,X,I sent alone.
- No self-collisions or impossible poses.
JUDGEMENT:
- Ambiguous/below-threshold → no_action with low confidence. Safer to refuse.
- Antagonist co-contraction → stop (S).
- Prefer smallest movement that satisfies intent.
- Report confidence honestly. Low-confidence correct refusal > high-confidence wrong.
- safety block is advisory; dishonesty=failure.
DETERMINISM:
- Identical input → identical output.
- detected_pattern: rest, power_grasp, precision_pinch, lateral_pinch, hand_open, wrist_flexion, co_contraction.
"""

AUTHORED_TECHNICAL_CONTEXT = """\
MECHANICS
6 DOF, 15 joints. One motor per finger (A-F). D1=thumb, D2=index, D3=middle, D4=ring, D5=pinky.
No individual phalanges.
COMMANDS (0=open, max=closed)
A(pinky 0-600), B(ring 0-550), C(middle 0-600), D(index 0-550), E(thumb_lower 0-130), F(thumb_upper 0-400)
GESTURES (single letter, no args)
O=OPEN, C=CLOSE, P=PINCH, R=SPIDERMAN, W=PARTIAL_CLAW, Y=OK, L=THUMBS_UP, M=CALL_ME, H=3, U=4, G=POINT, S=STOP, X=CAL, I=INIT
System: S,X,I alone. Bare C=CLOSE, C400=middle finger.
COUPLING
A/B/C/D: P(0-90°×1.00), I(0-100°×0.95), D(0-70°×0.70)
E: R(0-60°×1.00)
F: P(0-55°×1.00), D(0-80°×0.85)
PROTOCOL
Bluetooth SPP 115200 baud, ASCII uppercase, comma-separated, newline, max 128 chars.
Valid: A320,B180,C400,D200 | E120,F350 | P | S
SAFETY
Max 6 actuators. Speed 5-100% (default 60). Duration 120-5000ms. Min 50ms between transmissions.
Avoid: fully flexed thumb + fully flexed index/middle (collision).
Return to OPEN at session end.
EMG INPUT
Matrix N×8 (int8 signed -128..127). CH1=Flexor_digitorum_superficialis, CH2=Flexor_carpi_radialis, CH3=Flexor_carpi_ulnaris, CH4=Palmaris_longus, CH5=Extensor_digitorum_communis, CH6=Extensor_carpi_radialis_longus, CH7=Extensor_carpi_ulnaris, CH8=Brachioradialis.
Read relatively, not absolute.
flexor_ratio = flexor RMS / (flexor RMS + extensor RMS)
- >0.65 → closing/grasping
- <0.35 → opening/extension
- ~0.5 with both strong → co-contraction = STOP
- all channels near floor → rest/no_action
OUTPUT
Valid JSON only. No prose.
{
  "hand":"right"|"left",
  "intent":"gesture"|"joint_positions"|"stop"|"no_action",
  "gesture":"O"|"C"|"P"|"R"|"W"|"Y"|"L"|"M"|"H"|"U"|"G"|"S"|"X"|"I"|null,
  "commands":[{"actuator":"A".."F","position":int,"speed_pct":5-100}],
  "serial_command":string,
  "confidence":float,
  "safety":{"within_limits":bool}
}"""


def _diff(actual: str, expected: str) -> str:
    """The first differing line, which is what a failure needs to point at."""
    for index, (got, want) in enumerate(
        zip(actual.splitlines(), expected.splitlines()), start=1
    ):
        if got != want:
            return f"line {index}\n  generated: {got!r}\n  authored : {want!r}"
    return f"line count: generated {len(actual.splitlines())}, authored {len(expected.splitlines())}"


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


def test_the_blocks_carry_the_versions_this_text_was_filed_under():
    """The seed keys artefacts on (name, version). If the text changes without
    the version moving, the seed silently keeps serving the old row and every
    execution is attributed to wording that was never sent."""
    assert SYSTEM_PROMPT_VERSION == "5.0.0"
    assert TECHNICAL_CONTEXT_VERSION == "4.0.0"
