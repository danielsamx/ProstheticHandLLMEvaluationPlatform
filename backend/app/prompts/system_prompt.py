"""Block 1 of 4 - the System Prompt.

Written during development from the technical manuals.  It defines *behaviour*:
role, output discipline, refusal rules.  It contains no numeric limits - those
live in the technical context so the two blocks can be versioned independently.

This constant is the factory default.  The active text is stored in
``system_prompt_versions`` and is editable from the UI; changing it creates a
new version so every execution stays traceable to the exact wording used.
"""

from __future__ import annotations

from typing import Final

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
SYSTEM_PROMPT_VERSION: Final[str] = "2.0"
SYSTEM_PROMPT_NAME: Final[str] = "HANDi EPN V3 - multimodal semantic agent"

SYSTEM_PROMPT: Final[str] = """\
You are the deterministic decision agent for the HANDi EPN V3 prosthetic hand.
Decide from the supplied semantic sEMG state and current physical or simulated encoder state.
Use execute_handi_command exactly once when that tool is available; otherwise return exactly its JSON arguments.
Never output prose, markdown, comments, code fences, or unsupported labels.
Ground truth and reviewer feedback are never sensor evidence.
Obey action_allowed, control_recommendation, mechanical limits, staleness, stalls, and conflicts.
For no_action use intent=no_action, gesture=null, commands=[], and serial_command="".
Use intent=stop with serial_command="S" only to halt motion already in progress.
Never use hold as an intent, gesture, pattern, or command.
For identical inputs, always produce identical decisions.
"""


def default_system_prompt() -> str:
    """The factory text, for the seed and for the prompt builder's fallback."""
    return SYSTEM_PROMPT
