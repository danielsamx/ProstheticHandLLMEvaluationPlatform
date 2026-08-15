"""Block 1 of 4 - the System Prompt.

Behaviour only: what the model is, what it receives, what it must return. No
numbers, no anatomy, no interpretation rules — those belong to blocks 2, 3 and 4
and are versioned separately, so a change to any of them does not reversion this
one.

Rewritten for the envelope-image flow. The previous text told the model it would
receive "exactly one surface EMG analysis window" and to weigh raw samples; it
now receives a *picture* of a processed envelope plus a small table, and never
sees a sample. A system prompt describing a stimulus that no longer arrives is
not merely stale — it primes the model to look for something absent and to
explain its absence.

Three things are stated here and nowhere else, because they are properties of
the *task* rather than of the hand or the signal:

* **One object, no prose.** The response is parsed by machine.
* **Three permitted answers.** The vocabulary lives in block 4 too, but a model
  that never reads that far must still not invent a command.
* **Inaction is a real answer.** Without saying so, an empty answer reads as a
  failure state and models avoid it, which turns an ambiguous window into a
  guess — and a guess moves a motor.

The stated shape is one field. It used to name four — `intent`, `gesture`,
`serial_command`, `confidence` — which asked the model to say the same thing
several ways and then let it disagree with itself: `intent: no_action` beside
`serial_command: "C"` is a real observed response, and the platform spent a
validation stage detecting it. One field cannot contradict itself.
"""

from __future__ import annotations

from typing import Final

#: Every block starts at 1.0.
SYSTEM_PROMPT_VERSION: Final[str] = "1.0"
SYSTEM_PROMPT_NAME: Final[str] = "HANDi EPN V3 - envelope image control layer"

SYSTEM_PROMPT: Final[str] = """\
You are the embedded control layer of the HANDi EPN V3 robotic prosthetic hand.
You receive one image of a processed surface EMG window and a table of descriptors derived from the same window.
Decide whether the user intends to open the hand, close the hand, or make no movement.
Output exactly one valid JSON object with exactly one field, gesture.
Do not output explanations, markdown, comments, code fences, additional fields or additional text.
The only permitted values of gesture are "O" to open, "C" to close, and "" to make no movement.
{"gesture": ""} is a valid and expected answer whenever the evidence does not clearly favour opening or closing.
Prefer {"gesture": ""} over a guess: an incorrect command moves a motor.
Base the decision on the image and the descriptors together, never on one alone.
For identical inputs, always produce identical outputs.
"""


def default_system_prompt() -> str:
    return SYSTEM_PROMPT
