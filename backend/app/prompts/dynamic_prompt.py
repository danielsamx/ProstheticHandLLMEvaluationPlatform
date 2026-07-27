"""Block 3 of 3 - the Dynamic Prompt.

The ONLY block that changes between executions.  It carries the raw EMG matrix,
the derived feature summary, the selected hand and the experiment metadata -
nothing else.  Keeping every other byte of the prompt frozen is what makes the
comparison between models causally attributable to the model or its sampling
configuration.

The template is a stored, editable artefact (``dynamic_prompt_templates``) so a
researcher can test alternative EMG renderings - matrix only, features only,
different decimation - as an independent variable.
"""

from __future__ import annotations

from typing import Any, Final

from app.domain.hand_spec import EMG_CHANNELS, EMG_CHANNEL_SITES, Handedness
from app.schemas.emg import EmgWindow
from app.services.emg_features import downsample

DYNAMIC_TEMPLATE_VERSION: Final[str] = "2.0.0"
DYNAMIC_TEMPLATE_NAME: Final[str] = "Raw 8-channel EMG matrix + derived features"

#: Rows printed in full before the matrix is decimated. 256 x 8 at 3 decimals is
#: roughly 4k tokens - enough signal for a model to work with, small enough to
#: leave room for the frozen context in a 32k window.
DEFAULT_MATRIX_MAX_ROWS: Final[int] = 256
DEFAULT_MATRIX_PRECISION: Final[int] = 3

DEFAULT_DYNAMIC_TEMPLATE: Final[str] = """\
# EXECUTION REQUEST

Hand: {hand}
Experiment: {experiment_type}
Acquisition: {source_mode} | {sample_count} samples @ {sample_rate_hz} Hz | {window_ms} ms
{subject_block}
## EMG MATRIX

Layout: {matrix_rows} rows x {channel_count} columns.
Row = one time step (ascending). Column order = {channel_order}.
Amplitudes are normalised to [-1.0, 1.0].{decimation_note}

{matrix_block}

## DERIVED FEATURES (computed from the full matrix, not the excerpt above)

{feature_block}

Aggregate activation (mean RMS): {mean_rms:.4f}
Flexor group CH1-CH4: {flexor:.4f} | Extensor group CH5-CH7: {extensor:.4f}
{extra_block}
Generate the prosthetic hand movement.
"""


def _ordinal(n: int) -> str:
    """1st, 2nd, 3rd, 4th … The model reads this text; "every 2th row" is noise."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def render_matrix_block(
    window: EmgWindow,
    *,
    max_rows: int = DEFAULT_MATRIX_MAX_ROWS,
    precision: int = DEFAULT_MATRIX_PRECISION,
) -> tuple[str, int, int]:
    """Render the sample matrix.

    Returns ``(text, rendered_rows, decimation_factor)``.  Decimation uses a
    uniform stride rather than averaging: averaging would smooth away the
    high-frequency content that the ZC and SSC features measure, and the model
    would see a signal inconsistent with the summary printed beside it.
    """
    rows, factor = downsample(window.samples, max_rows)
    lines = [
        "[" + ", ".join(f"{value:+.{precision}f}" for value in row) + "]"
        for row in rows
    ]
    return "\n".join(lines), len(rows), factor


def render_feature_block(window: EmgWindow, *, include_sites: bool = True) -> str:
    """Per-channel descriptor table."""
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
    return "\n".join(lines)


def render_dynamic_prompt(
    window: EmgWindow,
    *,
    handedness: Handedness,
    experiment_type: str = "single_inference",
    subject_ref: str | None = None,
    subject_notes: str | None = None,
    extra_parameters: dict[str, Any] | None = None,
    template: str | None = None,
    include_sites: bool = True,
    matrix_max_rows: int = DEFAULT_MATRIX_MAX_ROWS,
    matrix_precision: int = DEFAULT_MATRIX_PRECISION,
) -> str:
    """Assemble the dynamic block for one execution.

    ``subject_ref`` is a pseudonymous identifier only.  No direct personal data
    is ever placed in a prompt or persisted alongside it.
    """
    subject_block = ""
    if subject_ref or subject_notes:
        lines = ["", "## SUBJECT"]
        if subject_ref:
            lines.append(f"Reference: {subject_ref}")
        if subject_notes:
            lines.append(f"Notes: {subject_notes}")
        subject_block = "\n".join(lines) + "\n"

    extra_block = ""
    if extra_parameters:
        lines = ["", "## EXPERIMENT PARAMETERS"]
        for key, value in sorted(extra_parameters.items()):
            lines.append(f"{key}: {value}")
        extra_block = "\n".join(lines) + "\n"

    matrix_block, rendered_rows, factor = render_matrix_block(
        window, max_rows=matrix_max_rows, precision=matrix_precision
    )
    decimation_note = ""
    if factor > 1:
        decimation_note = (
            f"\nNOTE: the full window holds {window.sample_count} rows; every "
            f"{_ordinal(factor)} row is shown below. The feature table is "
            "computed from the complete window."
        )

    body = template or DEFAULT_DYNAMIC_TEMPLATE
    return body.format(
        hand=handedness.value.capitalize(),
        experiment_type=experiment_type,
        source_mode=window.source_mode.value,
        sample_count=window.sample_count,
        sample_rate_hz=window.sample_rate_hz,
        window_ms=window.window_ms,
        subject_block=subject_block,
        matrix_rows=rendered_rows,
        channel_count=len(EMG_CHANNELS),
        channel_order=", ".join(EMG_CHANNELS),
        decimation_note=decimation_note,
        matrix_block=matrix_block,
        feature_block=render_feature_block(window, include_sites=include_sites),
        mean_rms=window.total_activation,
        flexor=window.flexor_activation,
        extensor=window.extensor_activation,
        extra_block=extra_block,
    )
