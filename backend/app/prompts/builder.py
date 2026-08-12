"""Automatic assembly of the final four-block prompt.

    +-----------------------------+
    |        SYSTEM PROMPT        |   frozen behaviour contract
    +-----------------------------+
                  +
    +-----------------------------+
    |     EMG KNOWLEDGE CONTEXT   |   frozen interpretation guidance
    +-----------------------------+
                  +
    +-----------------------------+
    |        IMAGE CONTEXT        |   frozen description of the plot
    +-----------------------------+
                  +
    +-----------------------------+
    |      TECHNICAL CONTEXT      |   frozen hardware contract, open/close only
    +-----------------------------+
                  |
                  v
      user turn: feature table + PNG
                  |
                  v
               LiteLLM
                  |
                  v
             JSON response

The order is deliberate. The two EMG blocks sit together because they answer one
question between them — *what am I looking at* — and the hardware contract comes
last, closest to the answer it constrains.

The researcher never writes this by hand. ``build_prompt`` is the single entry
point used by the execution service and by the preview endpoint, and it also
produces the SHA-256 digests that let us prove after the fact that two runs saw
byte-identical inputs.

There is one flow. The selectable dynamic block — raw matrix, features, both,
semantic — is gone, along with the stored template that rendered it: with the
picture as the stimulus, printing the matrix beside it sent the model two
representations of the same window, processed differently, and let it choose
which to believe.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.domain.hand_spec import Handedness, LimitProfile, get_limit_profile
from app.prompts.emg_context import build_emg_context
from app.prompts.image_context import build_image_context
from app.prompts.system_prompt import default_system_prompt
from app.prompts.technical_context import build_technical_context_open_close
from app.schemas.emg import EmgWindow
from app.services.analysis_service import (
    DEFAULT_FEATURE_SOURCE,
    FeatureSource,
    analyse,
    applied_bandpass_high_hz,
    render_feature_block,
)

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
    image_context: str
    #: The user turn's text: the derived feature table.
    #:
    #: Still called ``dynamic_prompt`` because that is the name of the column it
    #: is persisted in and of the field the interface reads. Renaming it is a
    #: migration, not an edit, and doing it here would leave the record and the
    #: code disagreeing about the same string.
    dynamic_prompt: str
    messages: list[dict[str, Any]]
    limit_profile: str
    #: The picture itself, as the data URL that travels in the user message.
    image_data_url: str | None = None
    image_sha256: str | None = None
    image_context_sha256: str = ""
    system_prompt_sha256: str = ""
    technical_context_sha256: str = ""
    emg_context_sha256: str = ""
    dynamic_prompt_sha256: str = ""
    full_prompt_sha256: str = ""
    #: Hash of every frozen block: system + EMG + image + technical.
    #:
    #: All four, not two. The EMG guidance changes what the model is told to
    #: conclude from the same signal, and the image context changes what it is
    #: told the picture means, so two runs that saw different guidance are not
    #: comparable — and if this hash ignored them, the platform would report
    #: them as comparable while they were not. That is a worse failure than
    #: reporting too few comparisons.
    frozen_context_sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def frozen_blocks(self) -> list[str]:
        """The frozen blocks, in the order the model reads them."""
        return [
            self.system_prompt,
            self.emg_context,
            self.image_context,
            self.technical_context,
        ]

    @property
    def frozen_context(self) -> str:
        """Everything identical between runs, in the order the model sees it."""
        return BLOCK_SEPARATOR.join(self.frozen_blocks)

    @property
    def full_prompt(self) -> str:
        """The text of the stimulus. Not the whole stimulus: the picture is not
        text and cannot appear here, which is why the image digest is carried
        separately and why this string alone never proves what was sent."""
        return BLOCK_SEPARATOR.join([*self.frozen_blocks, self.dynamic_prompt])

    def char_counts(self) -> dict[str, int]:
        return {
            "system_prompt": len(self.system_prompt),
            "technical_context": len(self.technical_context),
            "emg_context": len(self.emg_context),
            "image_context": len(self.image_context),
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
    limit_profile: LimitProfile | None = None,
    experiment_type: str = "single_inference",
    merge_context_into_system: bool = True,
    feature_source: FeatureSource | str = DEFAULT_FEATURE_SOURCE,
    feedback_note: str | None = None,
) -> AssembledPrompt:
    """Assemble the final prompt.

    Parameters
    ----------
    merge_context_into_system
        When ``True`` (default) the frozen blocks form the system message and
        only the feature table and the picture become the user turn. This keeps
        the frozen material in the system role, which is what most providers
        cache and what keeps the user turn minimal — exactly the separation the
        experimental design requires. Set to ``False`` for runtimes (some LM
        Studio presets) that handle long system messages poorly; the context
        then becomes a leading user message.
    feature_source
        The preprocessing toggle. Governs the picture and the table together —
        see :mod:`app.services.analysis_service`.
    feedback_note
        Appended to the user turn by the corrective-retry path, which re-runs a
        window with a reviewer's account of what the hand actually did. The one
        sanctioned way to add text to the user turn: it exists so that path does
        not need a general template mechanism, whose only other use was to let a
        stored artefact silently replace the stimulus.

    The technical context defaults to the open/close variant, not the full
    fourteen-gesture contract: the reduced vocabulary is only meaningful if that
    table is *gone*, since leaving it in place and adding "but only answer O or
    C" would give the model two contradictory contracts and let it pick. The
    seed stores that same reduced text, so a stored artefact passed here agrees
    with the default instead of quietly reinstating the old contract.

    The image context is not an argument at all. It has to describe the filter
    that actually ran on *this* window — clamped by its sampling rate, or absent
    entirely when the toggle is off — so it cannot be a stored text that was
    written before the window existed.
    """
    profile = limit_profile or get_limit_profile()

    analysis = analyse(
        window.samples,
        sample_rate_hz=window.sample_rate_hz,
        feature_source=feature_source,
    )

    system_text = system_prompt if system_prompt is not None else default_system_prompt()
    emg_text = emg_context if emg_context is not None else build_emg_context()
    image_context_text = build_image_context(
        preprocessed=analysis.feature_source is FeatureSource.PREPROCESSED,
        bandpass_high_hz=applied_bandpass_high_hz(analysis.preprocessing),
    )
    context_text = (
        technical_context
        if technical_context is not None
        else build_technical_context_open_close()
    )

    dynamic_text = render_feature_block(analysis.features)
    if feedback_note:
        dynamic_text = f"{dynamic_text}\n\n{feedback_note}"

    blocks = [system_text, emg_text, image_context_text, context_text]
    frozen = BLOCK_SEPARATOR.join(blocks)

    # The user turn carries text plus the picture. A multimodal turn is a list of
    # typed parts rather than a string, which is why a model without vision
    # cannot be offered for this flow at all.
    user_content: Any = [
        {"type": "text", "text": dynamic_text},
        {"type": "image_url", "image_url": {"url": analysis.image.data_url}},
    ] if analysis.image else dynamic_text

    if merge_context_into_system:
        messages = [
            {"role": "system", "content": frozen},
            {"role": "user", "content": user_content},
        ]
    else:
        leading = BLOCK_SEPARATOR.join([*blocks[1:], dynamic_text])
        messages = [
            {"role": "system", "content": system_text},
            {
                "role": "user",
                "content": (
                    [
                        {"type": "text", "text": leading},
                        {"type": "image_url", "image_url": {"url": analysis.image.data_url}},
                    ]
                    if analysis.image
                    else leading
                ),
            },
        ]

    assembled = AssembledPrompt(
        system_prompt=system_text,
        technical_context=context_text,
        emg_context=emg_text,
        image_context=image_context_text,
        dynamic_prompt=dynamic_text,
        messages=messages,
        limit_profile=profile.id.value,
        metadata={
            "handedness": handedness.value,
            "experiment_type": experiment_type,
            "emg_source_mode": window.source_mode.value,
            "merge_context_into_system": merge_context_into_system,
            **analysis.provenance(),
            "features": analysis.features,
        },
    )
    assembled.image_data_url = analysis.image.data_url if analysis.image else None
    assembled.image_sha256 = analysis.image.sha256 if analysis.image else None

    assembled.system_prompt_sha256 = sha256(system_text)
    assembled.technical_context_sha256 = sha256(context_text)
    assembled.emg_context_sha256 = sha256(emg_text)
    assembled.image_context_sha256 = sha256(image_context_text)
    assembled.dynamic_prompt_sha256 = sha256(dynamic_text)
    assembled.frozen_context_sha256 = sha256(assembled.frozen_context)
    assembled.full_prompt_sha256 = sha256(assembled.full_prompt)

    # The image is part of the stimulus but not part of any text block, so it
    # cannot reach `frozen_context_sha256` — which is correct: the digest is the
    # *comparability* key, and two runs over different windows with the same
    # blocks are still comparable. The image identity is carried separately, on
    # the execution, where it belongs.
    return assembled
