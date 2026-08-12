"""Prompt size estimation and the context budget.

Guards the failure that produced:

    request (16676 tokens) exceeds the available context size (8192 tokens)

Three causes, all gone: the full JSON Schema was embedded in the prompt *and*
sent as `response_format`; the fourteen-gesture contract was sent for a task with
three answers; and the whole sample matrix was printed as text.

The last of those is why several tests here changed rather than moved. The
prompt no longer grows with the recording — the user turn is eight rows of
descriptors and a picture — so the tests that pinned "it grows, and the advice
names a row count you can cut" were pinning a control that no longer exists.
What replaces them is the opposite property: that the size is fixed.
"""

from __future__ import annotations

import pytest

from app.prompts.budget import check, estimate_tokens
from app.prompts.builder import build_prompt
from app.services.emg_service import synthesise_window

# ── Estimation ──────────────────────────────────────────────────────────────


def test_numeric_content_is_not_estimated_like_prose():
    """A characters/4 heuristic under-counted a real prompt by more than half.
    The feature table is almost entirely numbers, and a signed three-decimal
    value costs three to four tokens across roughly six characters."""
    numbers = ", ".join("-0.004" for _ in range(100))
    prose = "the quick brown fox jumps over the lazy dog " * 15

    assert len(numbers) == pytest.approx(len(prose), rel=0.3)
    assert estimate_tokens(numbers) > estimate_tokens(prose) * 1.5


def test_empty_text_costs_nothing():
    assert estimate_tokens("") == 0


def test_the_prompt_does_not_grow_with_the_recording():
    """A 4,000-sample window costs what a 32-sample window costs.

    This is the property the whole flow buys. It also means a researcher can no
    longer overflow a context by importing a longer CSV, which was a real
    failure mode of the text flow and had nothing to do with the science.
    """
    small = estimate_tokens(build_prompt(
        synthesise_window("rest", seed=1, samples=32)).dynamic_prompt)
    large = estimate_tokens(build_prompt(
        synthesise_window("rest", seed=1, samples=4000)).dynamic_prompt)

    assert abs(large - small) / small < 0.15


# ── Budget ──────────────────────────────────────────────────────────────────


def _report(samples: int = 404, context_window: int | None = 8192, **kwargs):
    prompt = build_prompt(synthesise_window("power_grasp", seed=1, samples=samples))
    return prompt, check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        emg_context=prompt.emg_context,
        image_context=prompt.image_context,
        context_window=context_window,
        **kwargs,
    )


def test_the_whole_prompt_fits_a_small_context():
    """Every block is frozen text of a known size, so this is now a property of
    the platform rather than of the recording someone happened to load."""
    _, report = _report()
    assert report.fits, report.summary()
    assert report.utilisation < 0.5


def test_an_oversized_prompt_is_flagged_with_advice():
    _, report = _report(context_window=2048)
    assert not report.fits
    assert report.advice
    assert any("context length" in line for line in report.advice)


def test_advice_leads_with_the_actionable_fix():
    _, report = _report(context_window=2048)
    assert "context length" in report.advice[0]


def test_the_advice_no_longer_offers_a_control_that_was_removed():
    """It used to say "cap the rows sent". There are no rows and no cap.

    Advice naming a setting the interface does not have sends the researcher
    looking for it, and finding nothing reads as a broken lab rather than as
    stale text.
    """
    _, report = _report(context_window=2048)
    joined = " ".join(report.advice)
    assert "rows" not in joined
    assert "The context length is the only lever." in joined


def test_a_large_completion_reserve_is_called_out():
    """Max tokens eats the same budget as the prompt, and the reply is a small
    JSON object — an easy win the researcher would not otherwise think of."""
    _, report = _report(samples=64, context_window=7000, completion_reserve=6144)
    assert not report.fits
    assert any("reserved for the reply" in line for line in report.advice)


def test_an_unknown_context_window_is_not_reported_as_a_failure():
    """Not knowing the limit is different from exceeding it."""
    _, report = _report(context_window=None)
    assert report.fits
    assert report.utilisation is None
    assert report.advice == []


def test_the_breakdown_covers_all_five_pieces_of_text():
    """A block missing from the breakdown is a block whose cost is invisible.

    Five, not four: the four frozen blocks plus the user turn. The picture is
    absent on purpose — see `test_the_estimate_is_a_floor_because_the_image_is_not_counted`.
    """
    _, report = _report()
    assert set(report.breakdown) == {
        "system_prompt", "technical_context", "emg_context",
        "image_context", "dynamic_prompt",
    }
    assert report.prompt_tokens == sum(report.breakdown.values())
    assert report.breakdown["emg_context"] > 0
    assert report.breakdown["image_context"] > 0


def test_the_estimate_is_a_floor_because_the_image_is_not_counted():
    """The picture occupies context and no figure here accounts for it.

    Its cost depends on the vision encoder and on the resolution the runtime
    rescales to, so any constant would be right for one model and wrong for the
    rest. Pinned as a known limitation rather than papered over with a guess: a
    padded number looks like a measurement.
    """
    prompt, report = _report()
    assert prompt.image_data_url is not None
    assert len(prompt.image_data_url) > 10_000
    # Nothing in the breakdown scales with the picture's size: the whole
    # estimate stays in the low thousands while the PNG alone is tens of
    # kilobytes of base64.
    assert report.prompt_tokens < 3_000


def test_completion_reserve_is_deducted():
    prompt = build_prompt(synthesise_window("rest", seed=1, samples=64))
    kwargs = dict(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        emg_context=prompt.emg_context,
        image_context=prompt.image_context,
        context_window=4096,
    )
    assert check(**kwargs, completion_reserve=128).fits
    assert not check(**kwargs, completion_reserve=3072).fits


# ── The size fixes ──────────────────────────────────────────────────────────


def test_the_schema_is_not_sent_twice():
    """`response_format` already carries the schema; embedding it in the prompt
    spent about 1,300 tokens restating a constraint the runtime enforces."""
    from app.prompts.technical_context import build_technical_context_open_close

    context = build_technical_context_open_close()
    assert '"$defs"' not in context
    assert estimate_tokens(context) < 4_500
