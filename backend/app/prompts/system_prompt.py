"""Block 1 of 3 - the System Prompt.

Written during development from the technical manuals.  It defines *behaviour*:
role, output discipline, refusal rules.  It contains no numeric limits - those
live in the technical context so the two blocks can be versioned independently.

This constant is the factory default.  The active text is stored in
``system_prompt_versions`` and is editable from the UI; changing it creates a
new version so every execution stays traceable to the exact wording used.
"""

from __future__ import annotations

from typing import Final

#: 3.0.0 - the response is the command line itself, not a JSON object wrapping
#:         it. Most of the old contract described fields the model asserted
#:         about its own reasoning, none of which the backend trusted.
#: 4.0.0 - the determinism instruction removed.
#: 5.0.0 - author-supplied text. Reverts to the structured JSON contract and
#:         restores the confidence, detected_pattern and safety fields, which
#:         makes the model's own account of its decision a recorded variable
#:         again. The backend still re-derives every safety property
#:         independently, so those fields are measured, never trusted: the
#:         `consistency` validation stage exists precisely to catch a
#:         `serial_command` that disagrees with the structure beside it.
SYSTEM_PROMPT_VERSION: Final[str] = "5.0.0"
SYSTEM_PROMPT_NAME: Final[str] = "HANDi EPN V3 - baseline controller"

SYSTEM_PROMPT: Final[str] = """\
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


def default_system_prompt() -> str:
    """The factory text, for the seed and for the prompt builder's fallback."""
    return SYSTEM_PROMPT
