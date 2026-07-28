"""Block 3 of 3 - the Dynamic Prompt.

The ONLY block that changes between executions. What it carries is now an
experimental variable in its own right, selected per run:

    MATRIX    the raw N x 8 sample matrix and nothing else
    FEATURES  the derived per-channel descriptors and nothing else
    BOTH      the matrix followed by the descriptors

That choice is the point. "Can an LLM read raw EMG?" and "can an LLM act on
extracted features?" are different questions, and the second is a far easier
one — a feature table has already had the signal processing done for it. Making
the mode a switch rather than a code edit means the two can be compared under
an identical frozen context, which is the only way the difference is
attributable to the input rather than to everything else that changed with it.

The matrix is sent whole by default. It was previously capped at 32 printed
rows, which kept the prompt inside a small context but meant the model saw an
eighth of an imported recording while the interface reported the full row
count — a discrepancy that would quietly invalidate any conclusion drawn from
it. Sending everything is the honest default; the cost is that a long recording
can exceed the runtime's context, which the budget check reports before the
request is made rather than after it fails.

The template remains a stored, editable artefact (``dynamic_prompt_templates``)
so a researcher can vary the rendering as an independent variable.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Final

from app.domain.hand_spec import EMG_CHANNEL_SITES, Handedness
from app.schemas.emg import EmgWindow
from app.services.emg_features import downsample


class DynamicContent(str, Enum):
    """What the dynamic block carries. One of the experiment's variables."""

    MATRIX = "matrix"
    FEATURES = "features"
    BOTH = "both"


#: 3.0.0 - the matrix carries raw converter output, so the block no longer
#:         claims a normalised amplitude range.
#: 4.0.0 - the matrix and nothing else.
#: 5.0.0 - the content is selectable (matrix / features / both) and the matrix
#:         is sent complete rather than decimated to 32 rows.
DYNAMIC_TEMPLATE_VERSION: Final[str] = "5.0.0"
DYNAMIC_TEMPLATE_NAME: Final[str] = "Selectable EMG matrix and derived features"

#: No cap. ``None`` means every row of the window is printed.
#:
#: A cap is still available per execution for researchers working against a
#: small context window, but it is no longer the default: silently showing the
#: model an eighth of the data while the UI reported the full count was a
#: discrepancy capable of invalidating a result without anyone noticing.
DEFAULT_MATRIX_MAX_ROWS: Final[int | None] = None
DEFAULT_MATRIX_PRECISION: Final[int] = 3

#: Roughly the token cost of one printed matrix row, measured against the
#: calibrated estimator. Used to tell a researcher how many rows their context
#: can take before they send a request that cannot fit.
APPROX_TOKENS_PER_ROW: Final[float] = 41.0

_MATRIX_TEMPLATE: Final[str] = "{matrix_block}"
_FEATURES_TEMPLATE: Final[str] = "{feature_block}"
_BOTH_TEMPLATE: Final[str] = "{matrix_block}\n\n{feature_block}"

TEMPLATES: Final[dict[DynamicContent, str]] = {
    DynamicContent.MATRIX: _MATRIX_TEMPLATE,
    DynamicContent.FEATURES: _FEATURES_TEMPLATE,
    DynamicContent.BOTH: _BOTH_TEMPLATE,
}

#: The default remains the matrix alone: it is the condition the platform exists
#: to measure, and the one a reader should assume when a run does not say.
DEFAULT_CONTENT: Final[DynamicContent] = DynamicContent.MATRIX


def render_matrix_block(
    window: EmgWindow,
    *,
    max_rows: int | None = DEFAULT_MATRIX_MAX_ROWS,
    precision: int = DEFAULT_MATRIX_PRECISION,
) -> tuple[str, int, int]:
    """Render the sample matrix, one row per time step, eight values per row.

    Returns ``(text, rendered_rows, decimation_factor)``. The factor is 1 when
    the whole window was printed, which is now the default.

    When a cap is set, decimation uses a uniform stride rather than averaging:
    averaging would smooth away the high-frequency content that distinguishes a
    co-contraction from a steady grasp, which is exactly the distinction the
    model is being asked to make.
    """
    if max_rows is None or max_rows >= window.sample_count:
        rows, factor = window.samples, 1
    else:
        rows, factor = downsample(window.samples, max_rows)

    lines = [
        "[" + ", ".join(f"{value:+.{precision}f}" for value in row) + "]"
        for row in rows
    ]
    return "\n".join(lines), len(rows), factor


def render_feature_block(window: EmgWindow, *, include_sites: bool = False) -> str:
    """Per-channel descriptors, computed over the complete window.

    Always the complete window, even when the printed matrix is capped: a
    summary of the excerpt would describe something the researcher never chose
    to analyse.
    """
    header = (
        "| CH  |    RMS |    MAV |  ZC |  SSC |     WL |    min |    max |"
        + (" Site" if include_sites else "")
    )
    divider = (
        "|-----|--------|--------|-----|------|--------|--------|--------|"
        + ("------" if include_sites else "")
    )
    lines = [header, divider]
    for feature in window.features:
        row = (
            f"| {feature.label} | {feature.rms:6.4f} | {feature.mav:6.4f} | "
            f"{feature.zc:3d} | {feature.ssc:4d} | {feature.wl:6.4f} | "
            f"{feature.min:+6.3f} | {feature.max:+6.3f} |"
        )
        if include_sites:
            row += f" {EMG_CHANNEL_SITES.get(feature.label, '')}"
        lines.append(row)

    lines.append("")
    lines.append(
        f"flexor_ratio {window.flexor_ratio:.3f} "
        f"(flexor {window.flexor_activation:.2f} / extensor {window.extensor_activation:.2f})"
    )
    return "\n".join(lines)


def rows_that_fit(available_tokens: int) -> int:
    """How many matrix rows a given token budget can hold.

    Used to turn "the prompt does not fit" into "your context holds about 140
    of these 404 rows", which is a number a researcher can act on.
    """
    return max(0, int(available_tokens / APPROX_TOKENS_PER_ROW))


def render_dynamic_prompt(
    window: EmgWindow,
    *,
    content: DynamicContent | str = DEFAULT_CONTENT,
    handedness: Handedness = Handedness.RIGHT,
    experiment_type: str = "single_inference",
    subject_ref: str | None = None,
    subject_notes: str | None = None,
    extra_parameters: dict[str, Any] | None = None,
    template: str | None = None,
    include_sites: bool = False,
    matrix_max_rows: int | None = DEFAULT_MATRIX_MAX_ROWS,
    matrix_precision: int = DEFAULT_MATRIX_PRECISION,
) -> str:
    """Assemble the dynamic block for one execution.

    An explicit ``template`` overrides ``content``: a stored template is a
    deliberate choice by the researcher, and silently replacing it with a
    built-in one would make the saved artefact a lie.

    ``subject_ref`` remains a pseudonymous identifier only. No direct personal
    data is ever placed in a prompt or persisted alongside one.
    """
    mode = DynamicContent(content) if not isinstance(content, DynamicContent) else content

    # The matrix is only rendered when it is going to be used. On a 4,000-row
    # recording formatting it costs real time, and doing that work to throw it
    # away would slow down exactly the feature-only runs that need it least.
    matrix_block, rendered_rows, factor = (
        render_matrix_block(window, max_rows=matrix_max_rows, precision=matrix_precision)
        if mode in (DynamicContent.MATRIX, DynamicContent.BOTH) or template
        else ("", 0, 1)
    )
    feature_block = (
        render_feature_block(window, include_sites=include_sites)
        if mode in (DynamicContent.FEATURES, DynamicContent.BOTH) or template
        else ""
    )

    body = template or TEMPLATES[mode]

    # A custom template may reference fields no built-in one uses. `format_map`
    # with a forgiving mapping leaves an unknown placeholder as written instead
    # of raising, so one stale saved template cannot take down an execution.
    return body.format_map(_Fields({
        "matrix_block": matrix_block,
        "feature_block": feature_block,
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
