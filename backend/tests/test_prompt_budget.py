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


def test_estimate_grows_with_the_matrix():
    small = build_prompt(synthesise_window("rest", seed=1, samples=32))
    large = build_prompt(synthesise_window("rest", seed=1, samples=400))
    assert estimate_tokens(large.dynamic_prompt) > estimate_tokens(small.dynamic_prompt)


# ── Budget ──────────────────────────────────────────────────────────────────


def _report(samples: int = 404, context_window: int | None = 8192):
    prompt = build_prompt(synthesise_window("power_grasp", seed=1, samples=samples))
    return prompt, check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        context_window=context_window,
    )


def test_the_default_prompt_fits_an_8k_context():
    """8k is LM Studio's usual default and a 3B model is a realistic target."""
    _, report = _report()
    assert report.fits, report.summary()
    assert report.utilisation < 0.9


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
        context_window=7000,
        completion_reserve=4096,
    )
    assert not report.fits
    assert any("reserved for the reply" in line for line in report.advice)


def test_the_capped_matrix_is_never_the_dominant_block():
    """Capping the printed rows is what makes the prompt size predictable: it no
    longer scales with the length of the recording."""
    for samples in (64, 404, 4000):
        _, report = _report(samples=samples)
        assert report.breakdown["dynamic_prompt"] <= report.breakdown["technical_context"]


def test_an_unknown_context_window_is_not_reported_as_a_failure():
    """Not knowing the limit is different from exceeding it."""
    _, report = _report(context_window=None)
    assert report.fits
    assert report.utilisation is None
    assert report.advice == []


def test_the_breakdown_covers_all_three_blocks():
    _, report = _report()
    assert set(report.breakdown) == {"system_prompt", "technical_context", "dynamic_prompt"}
    assert report.prompt_tokens == sum(report.breakdown.values())


def test_completion_reserve_is_deducted():
    prompt = build_prompt(synthesise_window("rest", seed=1, samples=64))
    kwargs = dict(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        context_window=8192,
    )
    assert check(**kwargs, completion_reserve=128).fits
    assert not check(**kwargs, completion_reserve=4096).fits


# ── The two size fixes ──────────────────────────────────────────────────────


def test_matrix_row_budget_stays_small():
    """256 rows cost roughly 6,700 tokens on their own — more than an 8k context
    can hold once the frozen blocks are added."""
    assert DEFAULT_MATRIX_MAX_ROWS <= 64


def test_the_schema_is_not_sent_twice():
    """`response_format` already carries the schema; embedding it in the prompt
    spent about 1,300 tokens restating a constraint the runtime enforces."""
    from app.prompts.technical_context import build_technical_context

    context = build_technical_context()
    assert '"$defs"' not in context
    assert estimate_tokens(context) < 4_500
