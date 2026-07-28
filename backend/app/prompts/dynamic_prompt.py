"""Block 3 of 3 - the Dynamic Prompt.

The ONLY block that changes between executions, and now it carries exactly one
thing: the raw EMG matrix. No headings, no hand, no acquisition metadata, no
derived feature table.

That is a real narrowing of what the model is given, and it is worth being
explicit about the consequences rather than discovering them in the results:

* **The features are gone from the prompt.** RMS, MAV, ZC, SSC and the
  flexor ratio are still computed, still stored on the window and still
  available to the analysis — but the model no longer receives them. It must
  derive amplitude balance from the numbers itself. This is the more honest
  experiment: a feature table is a preprocessing step, and the platform's
  question is what an LLM can do with raw EMG.

* **The hand is gone from the prompt.** The response schema still requires a
  `hand` field, so the model must now guess it. The pipeline compares what it
  says against the hand the execution was configured for and records a
  mismatch as a warning rather than a failure — blocking on it would fail
  every response from a model that simply defaults to "right".

* **Nothing identifies the window.** Two executions over the same matrix
  produce byte-identical prompts, which is what makes repetition groups
  meaningful, but it also means the prompt alone no longer says which subject
  or session a run came from. That provenance lives in the execution record,
  which is where an auditor should be reading it from anyway.

The template remains a stored, editable artefact (``dynamic_prompt_templates``)
so a researcher can restore the features or the metadata as an independent
variable and measure what they were worth.
"""

from __future__ import annotations

from typing import Any, Final

from app.domain.hand_spec import Handedness
from app.schemas.emg import EmgWindow
from app.services.emg_features import downsample

#: 3.0.0 - the matrix carries raw converter output, so the block no longer
#:         claims a normalised amplitude range.
#: 4.0.0 - the matrix and nothing else.
DYNAMIC_TEMPLATE_VERSION: Final[str] = "4.0.0"
DYNAMIC_TEMPLATE_NAME: Final[str] = "Raw 8-channel EMG matrix"

#: Rows printed before the matrix is decimated.
#:
#: Chosen so the default prompt fits an 8,192-token context, which is what LM
#: Studio loads models with unless told otherwise — and therefore what most
#: researchers will hit first.
#:
#: At 256 rows the matrix alone cost roughly 6,700 tokens and overflowed that
#: context before the frozen blocks were added. 32 rows preserves the envelope
#: and the onset shape, which is what the decision turns on, and a 3B model
#: cannot use finer temporal detail anyway.
#:
#: Raise it (with the runtime's context length) when the model can take it.
DEFAULT_MATRIX_MAX_ROWS: Final[int] = 32
DEFAULT_MATRIX_PRECISION: Final[int] = 3

#: The whole template. A single substitution: there is nothing else to say.
DEFAULT_DYNAMIC_TEMPLATE: Final[str] = "{matrix_block}"


def render_matrix_block(
    window: EmgWindow,
    *,
    max_rows: int = DEFAULT_MATRIX_MAX_ROWS,
    precision: int = DEFAULT_MATRIX_PRECISION,
) -> tuple[str, int, int]:
    """Render the sample matrix.

    Returns ``(text, rendered_rows, decimation_factor)``. Decimation uses a
    uniform stride rather than averaging: averaging would smooth away the
    high-frequency content that distinguishes a co-contraction from a steady
    grasp, which is exactly the distinction the model is being asked to make.

    The factor is returned rather than announced in the prompt. Under a
    matrix-only contract there is nowhere to put a note, so the fact that a
    window was decimated is recorded on the execution instead — where it stays
    queryable rather than being buried in prompt text.
    """
    rows, factor = downsample(window.samples, max_rows)
    lines = [
        "[" + ", ".join(f"{value:+.{precision}f}" for value in row) + "]"
        for row in rows
    ]
    return "\n".join(lines), len(rows), factor


def render_dynamic_prompt(
    window: EmgWindow,
    *,
    handedness: Handedness = Handedness.RIGHT,
    experiment_type: str = "single_inference",
    subject_ref: str | None = None,
    subject_notes: str | None = None,
    extra_parameters: dict[str, Any] | None = None,
    template: str | None = None,
    include_sites: bool = False,
    matrix_max_rows: int = DEFAULT_MATRIX_MAX_ROWS,
    matrix_precision: int = DEFAULT_MATRIX_PRECISION,
) -> str:
    """Assemble the dynamic block: the matrix, and nothing else.

    The signature keeps every parameter the previous contract accepted. They
    are unused by the default template and are passed through to a custom one,
    so a stored template that reinstates the hand or the subject reference
    still renders. Dropping the parameters instead would have broken every
    caller and every saved template at once, for no gain.

    ``subject_ref`` remains a pseudonymous identifier only. No direct personal
    data is ever placed in a prompt or persisted alongside one.
    """
    matrix_block, rendered_rows, factor = render_matrix_block(
        window, max_rows=matrix_max_rows, precision=matrix_precision
    )

    body = template or DEFAULT_DYNAMIC_TEMPLATE

    # A custom template may reference any of the old fields. `format_map` with a
    # forgiving mapping leaves an unknown placeholder as written instead of
    # raising, so one stale template cannot take down an execution.
    return body.format_map(_Fields({
        "matrix_block": matrix_block,
        "matrix_rows": rendered_rows,
        "decimation_factor": factor,
        "hand": handedness.value.capitalize(),
        "experiment_type": experiment_type,
        "source_mode": window.source_mode.value,
        "sample_count": window.sample_count,
        "sample_rate_hz": window.sample_rate_hz,
        "window_ms": window.window_ms,
        "subject_ref": subject_ref or "",
        "subject_notes": subject_notes or "",
        "mean_rms": window.total_activation,
        "flexor": window.flexor_activation,
        "extensor": window.extensor_activation,
        "flexor_ratio": window.flexor_ratio,
        "extra_parameters": extra_parameters or {},
    }))


class _Fields(dict):
    """Leaves unknown placeholders intact rather than raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
