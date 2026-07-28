"""Prompt size estimation and the context budget.

Guards the failure that produced:

    request (16676 tokens) exceeds the available context size (8192 tokens)

Two causes, both fixed: the full JSON Schema was embedded in the prompt *and*
sent as `response_format`, and 256 matrix rows were printed when 64 carry the
same decision.
"""

from __future__ import annotations

import pytest

from app.prompts.budget import check, estimate_tokens
from app.prompts.builder import build_prompt
from app.prompts.dynamic_prompt import DEFAULT_MATRIX_MAX_ROWS
from app.services.emg_service import synthesise_window


# ── Estimation ──────────────────────────────────────────────────────────────


def test_numeric_content_is_not_estimated_like_prose():
    """A characters/4 heuristic under-counted a real prompt by more than half.
    An EMG matrix is almost entirely numbers, and a signed three-decimal value
    costs three to four tokens across roughly six characters."""
    numbers = ", ".join("-0.004" for _ in range(100))
    prose = "the quick brown fox jumps over the lazy dog " * 15

    assert len(numbers) == pytest.approx(len(prose), rel=0.3)
    assert estimate_tokens(numbers) > estimate_tokens(prose) * 1.5


def test_empty_text_costs_nothing():
    assert estimate_tokens("") == 0


def test_the_prompt_grows_with_the_recording_because_the_whole_matrix_is_sent():
    """The consequence of sending N rows instead of a fixed excerpt.

    A researcher *can* now overflow a model by loading a longer CSV. That is
    the trade accepted when the cap was removed, and it is preferable to the
    alternative, which was showing the model an eighth of the data while
    reporting the full row count.
    """
    small = estimate_tokens(build_prompt(
        synthesise_window("rest", seed=1, samples=32)).dynamic_prompt)
    large = estimate_tokens(build_prompt(
        synthesise_window("rest", seed=1, samples=400)).dynamic_prompt)

    assert large > small * 10


def test_the_features_block_does_not_grow_with_the_recording():
    """Eight rows of descriptors whatever the window length — which is what
    makes features-only a usable fallback on a small context."""
    from app.prompts.dynamic_prompt import DynamicContent

    small = estimate_tokens(build_prompt(
        synthesise_window("rest", seed=1, samples=32),
        dynamic_content=DynamicContent.FEATURES).dynamic_prompt)
    large = estimate_tokens(build_prompt(
        synthesise_window("rest", seed=1, samples=4000),
        dynamic_content=DynamicContent.FEATURES).dynamic_prompt)

    assert abs(large - small) / small < 0.15


# ── Budget ──────────────────────────────────────────────────────────────────


def _report(samples: int = 404, context_window: int | None = 8192):
    prompt = build_prompt(synthesise_window("power_grasp", seed=1, samples=samples))
    return prompt, check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        emg_context=prompt.emg_context,
        context_window=context_window,
        matrix_rows=prompt.metadata["matrix_rows_sent"],
    )


def test_the_frozen_blocks_stay_a_small_fraction_of_a_small_context():
    """The two blocks sent on every single run. Whatever the matrix costs, these
    are the fixed overhead subtracted from it, so they have to stay cheap."""
    _, report = _report()
    fixed = report.breakdown["system_prompt"] + report.breakdown["technical_context"]
    assert fixed < 0.25 * 8192, fixed


def test_an_oversized_prompt_is_flagged_with_advice():
    _, report = _report(context_window=2048)
    assert not report.fits
    assert report.advice
    assert any("context length" in line for line in report.advice)


def test_advice_leads_with_the_actionable_fix():
    _, report = _report(context_window=2048)
    assert "context length" in report.advice[0]


def test_a_large_completion_reserve_is_called_out():
    """Max tokens eats the same budget as the prompt, and the reply is a small
    JSON object — an easy win the researcher would not otherwise think of."""
    prompt = build_prompt(synthesise_window("rest", seed=1, samples=64))
    report = check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        emg_context=prompt.emg_context,
        context_window=7000,
        completion_reserve=6144,
    )
    assert not report.fits
    assert any("reserved for the reply" in line for line in report.advice)


def test_the_advice_names_a_row_count_the_researcher_can_act_on():
    """"10,286 tokens over budget" is not actionable; "this context holds about
    159 of your 404 rows" is. The number has to be in the units of the control
    that exists."""
    _, report = _report(samples=404, context_window=8192)
    assert not report.fits
    assert any("rows alongside the frozen blocks" in line for line in report.advice)


def test_an_unknown_context_window_is_not_reported_as_a_failure():
    """Not knowing the limit is different from exceeding it."""
    _, report = _report(context_window=None)
    assert report.fits
    assert report.utilisation is None
    assert report.advice == []


def test_the_breakdown_covers_all_four_blocks():
    """A block missing from the breakdown is a block whose cost is invisible,
    and the EMG context is frozen — paid on every single run."""
    _, report = _report()
    assert set(report.breakdown) == {
        "system_prompt", "technical_context", "emg_context", "dynamic_prompt",
    }
    assert report.prompt_tokens == sum(report.breakdown.values())
    assert report.breakdown["emg_context"] > 0


def test_completion_reserve_is_deducted():
    prompt = build_prompt(synthesise_window("rest", seed=1, samples=64))
    kwargs = dict(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        emg_context=prompt.emg_context,
        context_window=8192,
    )
    assert check(**kwargs, completion_reserve=128).fits
    assert not check(**kwargs, completion_reserve=6144).fits


# ── The two size fixes ──────────────────────────────────────────────────────


def test_the_matrix_is_uncapped_by_default():
    """N rows x 8 columns, complete. A default cap would silently discard most
    of an imported recording."""
    assert DEFAULT_MATRIX_MAX_ROWS is None


def test_the_schema_is_not_sent_twice():
    """`response_format` already carries the schema; embedding it in the prompt
    spent about 1,300 tokens restating a constraint the runtime enforces."""
    from app.prompts.technical_context import build_technical_context

    context = build_technical_context()
    assert '"$defs"' not in context
    assert estimate_tokens(context) < 4_500
