"""Block 4 of 4 - the Dynamic Prompt.

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
from app.schemas.multimodal import MechanicalTelemetry
from app.services.emg_features import downsample
from app.services.semantic_serializer import serialize_multimodal_state


class DynamicContent(str, Enum):
    """What the dynamic block carries. One of the experiment's variables."""

    MATRIX = "matrix"
    FEATURES = "features"
    BOTH = "both"
    SEMANTIC = "semantic"


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
DYNAMIC_TEMPLATE_VERSION: Final[str] = "1.0"
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
_SEMANTIC_TEMPLATE: Final[str] = """\
MULTIMODAL SEMANTIC STATE (derived deterministically; ground truth is never included)
{semantic_block}
Follow control_recommendation and use only output-contract labels.
For no_action set intent=no_action, gesture=null, commands=[], and serial_command="".
Copy detected_pattern_hint when it is not unknown.
Use intent=stop with serial_command="S" only to halt motion already in progress.
Never use hold as intent, gesture, detected_pattern, or command.
Never command motion farther into a limit or stall.
"""

TEMPLATES: Final[dict[DynamicContent, str]] = {
    DynamicContent.MATRIX: _MATRIX_TEMPLATE,
    DynamicContent.FEATURES: _FEATURES_TEMPLATE,
    DynamicContent.BOTH: _BOTH_TEMPLATE,
    DynamicContent.SEMANTIC: _SEMANTIC_TEMPLATE,
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


def rendered_row_count(
    window: EmgWindow,
    *,
    content: DynamicContent | str = DEFAULT_CONTENT,
    max_rows: int | None = DEFAULT_MATRIX_MAX_ROWS,
    template: str | None = None,
) -> int:
    """How many matrix rows the prompt will actually contain.

    Not ``min(sample_count, max_rows)``. Decimation uses a uniform stride, so a
    cap of 64 on a 100-row window yields 50 rows, not 64 — the stride is 2 and
    there is no half-step. Reporting the requested figure instead of the real
    one would put a number in the execution record that no prompt ever had.
    """
    mode = DynamicContent(content) if not isinstance(content, DynamicContent) else content
    body = template if not is_builtin_template(template) else None
    body = body or TEMPLATES[mode]
    if "{matrix_block}" not in body:
        return 0
    if max_rows is None or max_rows >= window.sample_count:
        return window.sample_count
    return len(downsample(window.samples, max_rows)[0])


def overriding_template(row) -> str | None:
    """The stored template, but only when it should defeat the mode switch.

    A `dynamic_prompt_templates` row arrives on every request, because the lab
    selects the active artefact automatically. Treating any of them as an
    override means the Matrix / Features / Both switch does nothing: the stored
    body wins and renders whatever it happens to reference.

    The rule is ownership, read from the row itself: a **system default** is one
    of the platform's own renderings and the mode switch is the way to choose
    between them, so it never overrides. A row a researcher authored is a
    deliberate decision and always does.

    This deliberately does *not* compare the text against the built-in
    templates. That was the first attempt and it was wrong in the one place it
    mattered — a database seeded by an earlier version holds an older default,
    whose text matches nothing current, so it was misread as hand-written and
    went on forcing the matrix into every prompt including feature-only ones.
    A flag on the row survives every version of the text; a string comparison
    only survives the current one.
    """
    if row is None or getattr(row, "is_system_default", False):
        return None
    return row.content


def is_builtin_template(template: str | None) -> bool:
    """Is this one of the renderings the mode switch already selects?

    The seed files the default rendering as a stored artefact, and the lab
    selects the active artefact automatically. So a template string arrives on
    every request whether or not the researcher ever touched one — and treating
    any template as an override meant the mode switch did nothing at all:
    choosing "features" still rendered the matrix, because the stored
    "{matrix_block}" won.

    A template identical to a built-in rendering is not an override. Only a
    template someone actually wrote is.
    """
    return template is not None and template in set(TEMPLATES.values())


def render_dynamic_prompt(
    window: EmgWindow,
    *,
    content: DynamicContent | str = DEFAULT_CONTENT,
    handedness: Handedness = Handedness.RIGHT,
    experiment_type: str = "single_inference",
    subject_ref: str | None = None,
    subject_notes: str | None = None,
    extra_parameters: dict[str, Any] | None = None,
    mechanical_telemetry: MechanicalTelemetry | None = None,
    mvc_by_channel: list[float] | None = None,
    template: str | None = None,
    include_sites: bool = False,
    matrix_max_rows: int | None = DEFAULT_MATRIX_MAX_ROWS,
    matrix_precision: int = DEFAULT_MATRIX_PRECISION,
) -> str:
    """Assemble the dynamic block for one execution.

    A *custom* ``template`` overrides ``content``: a hand-written template is a
    deliberate choice, and silently replacing it with a built-in rendering
    would make the saved artefact a lie. A template that merely equals one of
    the built-in renderings is not an override — see `is_builtin_template`.

    ``subject_ref`` remains a pseudonymous identifier only. No direct personal
    data is ever placed in a prompt or persisted alongside one.
    """
    mode = DynamicContent(content) if not isinstance(content, DynamicContent) else content
    custom = None if is_builtin_template(template) else template
    if mode is DynamicContent.SEMANTIC and (
        custom is None or "{semantic_block}" not in custom
    ):
        custom = None
    body = custom or TEMPLATES[mode]

    # Render only the blocks the body actually references.
    #
    # This is what makes the mode switch real: under "features" the matrix is
    # never built, so it cannot leak into the prompt. On a 4,000-row recording
    # it also saves formatting work that would only be discarded.
    wants_matrix = "{matrix_block}" in body
    wants_features = "{feature_block}" in body

    matrix_block, rendered_rows, factor = (
        render_matrix_block(window, max_rows=matrix_max_rows, precision=matrix_precision)
        if wants_matrix else ("", 0, 1)
    )
    feature_block = (
        render_feature_block(window, include_sites=include_sites)
        if wants_features else ""
    )

    # A custom template may reference fields no built-in one uses. `format_map`
    # with a forgiving mapping leaves an unknown placeholder as written instead
    # of raising, so one stale saved template cannot take down an execution.
    semantic_block = ""
    if mode is DynamicContent.SEMANTIC:
        semantic_block = serialize_multimodal_state(
            window, mechanical_telemetry, mvc_by_channel=mvc_by_channel
        ).model_dump_json(exclude_none=True)

    rendered = body.format_map(_Fields({
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
        "semantic_block": semantic_block,
    }))
    return rendered


class _Fields(dict):
    """Leaves unknown placeholders intact rather than raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
