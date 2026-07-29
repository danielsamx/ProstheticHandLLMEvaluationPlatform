"""Automatic assembly of the final four-block prompt.

    +-----------------------------+
    |        SYSTEM PROMPT        |   frozen behaviour contract
    +-----------------------------+
                  +
    +-----------------------------+
    |      TECHNICAL CONTEXT      |   frozen hardware description
    +-----------------------------+
                  +
    +-----------------------------+
    |     EMG KNOWLEDGE CONTEXT   |   frozen interpretation guidance
    +-----------------------------+
                  +
    +-----------------------------+
    |       DYNAMIC PROMPT        |   the EMG window for this run
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
    rendered_row_count,
)
from app.prompts.emg_context import build_emg_context
from app.prompts.system_prompt import default_system_prompt
from app.prompts.technical_context import build_technical_context
from app.schemas.emg import EmgWindow

#: Separator between blocks.
#:
#: A blank line. It used to be a rule of 78 equals signs, on the theory that a
#: model flattening the messages needed a hard visual boundary. It did not: each
#: block already opens with its own heading, so the rule marked a division the
#: text states anyway — while costing about 30 tokens per prompt and turning the
#: full-prompt view into something you have to read around.
BLOCK_SEPARATOR = "\n\n"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class AssembledPrompt:
    """Everything that was sent to the model, plus provenance hashes."""

    system_prompt: str
    technical_context: str
    emg_context: str
    dynamic_prompt: str
    messages: list[dict[str, str]]
    limit_profile: str
    system_prompt_sha256: str = ""
    technical_context_sha256: str = ""
    emg_context_sha256: str = ""
    dynamic_prompt_sha256: str = ""
    full_prompt_sha256: str = ""
    #: Hash of every frozen block: system + technical context + EMG context.
    #:
    #: All three now, not two. The EMG guidance changes what the model is told
    #: to conclude from the same signal, so two runs that saw different guidance
    #: are not comparable — and if this hash ignored block 3, the platform would
    #: report them as comparable while they were not. That is a worse failure
    #: than reporting too few comparisons.
    frozen_context_sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def frozen_context(self) -> str:
        """Everything identical between runs, in the order the model sees it."""
        return BLOCK_SEPARATOR.join(
            [self.system_prompt, self.technical_context, self.emg_context]
        )

    @property
    def full_prompt(self) -> str:
        return BLOCK_SEPARATOR.join(
            [
                self.system_prompt,
                self.technical_context,
                self.emg_context,
                self.dynamic_prompt,
            ]
        )

    def char_counts(self) -> dict[str, int]:
        return {
            "system_prompt": len(self.system_prompt),
            "technical_context": len(self.technical_context),
            "emg_context": len(self.emg_context),
            "dynamic_prompt": len(self.dynamic_prompt),
            "total": len(self.full_prompt),
        }


def build_prompt(
    window: EmgWindow,
    *,
    handedness: Handedness = Handedness.RIGHT,
    system_prompt: str | None = None,
    technical_context: str | None = None,
    emg_context: str | None = None,
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
    emg_text = emg_context if emg_context is not None else build_emg_context()
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

    frozen = BLOCK_SEPARATOR.join([system_text, context_text, emg_text])

    if merge_context_into_system:
        messages = [
            {"role": "system", "content": frozen},
            {"role": "user", "content": dynamic_text},
        ]
    else:
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": BLOCK_SEPARATOR.join(
                [context_text, emg_text, dynamic_text]
            )},
        ]

    assembled = AssembledPrompt(
        system_prompt=system_text,
        technical_context=context_text,
        emg_context=emg_text,
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
            "matrix_rows_sent": rendered_row_count(
                window,
                content=dynamic_content,
                max_rows=matrix_max_rows,
                template=dynamic_template,
            ),
        },
    )
    assembled.system_prompt_sha256 = sha256(system_text)
    assembled.technical_context_sha256 = sha256(context_text)
    assembled.emg_context_sha256 = sha256(emg_text)
    assembled.dynamic_prompt_sha256 = sha256(dynamic_text)
    assembled.frozen_context_sha256 = sha256(assembled.frozen_context)
    assembled.full_prompt_sha256 = sha256(assembled.full_prompt)
    return assembled
