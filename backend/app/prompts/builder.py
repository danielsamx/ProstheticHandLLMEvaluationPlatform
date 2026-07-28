"""Automatic assembly of the final three-block prompt.

    +-----------------------------+
    |        SYSTEM PROMPT        |   frozen behaviour contract
    +-----------------------------+
                  +
    +-----------------------------+
    |      TECHNICAL CONTEXT      |   frozen hardware description
    +-----------------------------+
                  +
    +-----------------------------+
    |       DYNAMIC PROMPT        |   EMG window, hand, experiment metadata
    +-----------------------------+
                  |
                  v
               LiteLLM
                  |
                  v
             JSON response

The researcher never writes this by hand.  ``build_prompt`` is the single entry
point used by the execution service, and it also produces the SHA-256 digests
that let us prove after the fact that two runs saw byte-identical inputs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.domain.hand_spec import Handedness, LimitProfile, get_limit_profile
from app.prompts.dynamic_prompt import (
    DEFAULT_CONTENT,
    DEFAULT_MATRIX_MAX_ROWS,
    DynamicContent,
    render_dynamic_prompt,
)
from app.prompts.system_prompt import default_system_prompt
from app.prompts.technical_context import build_technical_context
from app.schemas.emg import EmgWindow

#: Separator between the frozen context and the per-run payload.  Kept explicit
#: so models that flatten messages still see a hard boundary.
BLOCK_SEPARATOR = "\n\n" + "=" * 78 + "\n\n"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class AssembledPrompt:
    """Everything that was sent to the model, plus provenance hashes."""

    system_prompt: str
    technical_context: str
    dynamic_prompt: str
    messages: list[dict[str, str]]
    limit_profile: str
    system_prompt_sha256: str = ""
    technical_context_sha256: str = ""
    dynamic_prompt_sha256: str = ""
    full_prompt_sha256: str = ""
    #: Hash of system + technical context only.  Two executions sharing this
    #: value were run under identical experimental conditions.
    frozen_context_sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def full_prompt(self) -> str:
        return BLOCK_SEPARATOR.join(
            [self.system_prompt, self.technical_context, self.dynamic_prompt]
        )

    def char_counts(self) -> dict[str, int]:
        return {
            "system_prompt": len(self.system_prompt),
            "technical_context": len(self.technical_context),
            "dynamic_prompt": len(self.dynamic_prompt),
            "total": len(self.full_prompt),
        }


def build_prompt(
    window: EmgWindow,
    *,
    handedness: Handedness = Handedness.RIGHT,
    system_prompt: str | None = None,
    technical_context: str | None = None,
    dynamic_template: str | None = None,
    dynamic_content: DynamicContent | str = DEFAULT_CONTENT,
    matrix_max_rows: int | None = DEFAULT_MATRIX_MAX_ROWS,
    limit_profile: LimitProfile | None = None,
    experiment_type: str = "single_inference",
    subject_ref: str | None = None,
    subject_notes: str | None = None,
    extra_parameters: dict[str, Any] | None = None,
    merge_context_into_system: bool = True,
) -> AssembledPrompt:
    """Assemble the final prompt.

    Parameters
    ----------
    merge_context_into_system
        When ``True`` (default) the technical context is appended to the system
        message and only the dynamic block becomes the user turn.  This keeps
        the frozen material in the system role, which is what most providers
        cache and what keeps the user turn minimal - exactly the separation the
        experimental design requires.  Set to ``False`` for providers or local
        runtimes (some LM Studio presets, for instance) that handle long system
        messages poorly; the context then becomes a leading user message.
    """
    profile = limit_profile or get_limit_profile()

    system_text = system_prompt if system_prompt is not None else default_system_prompt()
    context_text = (
        technical_context
        if technical_context is not None
        else build_technical_context(profile)
    )
    dynamic_text = render_dynamic_prompt(
        window,
        content=dynamic_content,
        matrix_max_rows=matrix_max_rows,
        handedness=handedness,
        experiment_type=experiment_type,
        subject_ref=subject_ref,
        subject_notes=subject_notes,
        extra_parameters=extra_parameters,
        template=dynamic_template,
    )

    if merge_context_into_system:
        messages = [
            {"role": "system", "content": system_text + BLOCK_SEPARATOR + context_text},
            {"role": "user", "content": dynamic_text},
        ]
    else:
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": context_text + BLOCK_SEPARATOR + dynamic_text},
        ]

    assembled = AssembledPrompt(
        system_prompt=system_text,
        technical_context=context_text,
        dynamic_prompt=dynamic_text,
        messages=messages,
        limit_profile=profile.id.value,
        metadata={
            "handedness": handedness.value,
            "experiment_type": experiment_type,
            "emg_source_mode": window.source_mode.value,
            "merge_context_into_system": merge_context_into_system,
            # Recorded because it changes what the model was shown. Two runs
            # over the same window with different content are different
            # experiments, and the record has to say which one happened.
            "dynamic_content": DynamicContent(dynamic_content).value,
            "matrix_rows_sent": window.sample_count if matrix_max_rows is None
            else min(window.sample_count, matrix_max_rows),
        },
    )
    assembled.system_prompt_sha256 = sha256(system_text)
    assembled.technical_context_sha256 = sha256(context_text)
    assembled.dynamic_prompt_sha256 = sha256(dynamic_text)
    assembled.frozen_context_sha256 = sha256(system_text + BLOCK_SEPARATOR + context_text)
    assembled.full_prompt_sha256 = sha256(assembled.full_prompt)
    return assembled
