"""Prompt size estimation and context-budget checks.

A prompt that overflows the runtime's context window fails at the provider with
a message the researcher cannot act on without reading the server log. Checking
before the request costs nothing and turns it into an explicit, fixable warning.

Estimation is deliberately conservative. Character-count heuristics are badly
wrong for this content: the feature table is almost entirely numbers, and a
signed three-decimal value like ``-0.004`` costs three to four tokens across
roughly six characters — where prose costs one token per four. Dividing by four
under-counted a real prompt by more than half.

The calibration below was derived when the prompt carried a full sample matrix,
so it is measured over far more numeric content than any prompt now contains.
It is kept because it is still the honest direction to err in — over-counting
warns early, under-counting fails at the provider — but it is no longer tuned to
this prompt's mix and should be re-derived if the budget check ever starts
firing on prompts that fit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Tokens per numeric literal. Measured against llama.cpp tokenisation of signed
#: three-decimal values, which is what the EMG matrix is made of.
TOKENS_PER_NUMBER: float = 3.2

#: Characters per token for prose. Slightly pessimistic on purpose: a warning
#: that never fires is worse than one that fires a little early.
CHARS_PER_PROSE_TOKEN: float = 3.6

#: Empirical correction against llama.cpp, measured on this exact content.
#:
#: Two prompts of very different size were rejected by LM Studio with an exact
#: token count in the message:
#:
#:     estimate 12052 -> runtime 16676   (x1.384)
#:     estimate  6335 -> runtime  8649   (x1.365)
#:
#: Agreeing to within 1.4% across a 2x size range means the shortfall is
#: systematic — the model's tokeniser splits this vocabulary more finely than
#: the heuristic assumes — so a single factor corrects it. Re-derive this if the
#: prompt structure changes substantially.
TOKENISER_CALIBRATION: float = 1.375

#: Head-room kept for the reply. Matches the seeded `max_tokens`.
#:
#: The response is a JSON object with up to six command entries, so 64 tokens —
#: enough for a bare command line — would truncate mid-object and turn a correct
#: decision into a parse failure. 320 covers the largest well-formed response
#: with margin. Truncation is the failure mode to avoid here: it is
#: indistinguishable from malformed output in the metrics, so it would be
#: recorded as the model's fault rather than the budget's.
DEFAULT_COMPLETION_RESERVE: int = 320

_NUMBER_RE = re.compile(r"[-+]?\d*\.\d+|\d+")


def estimate_tokens(text: str) -> int:
    """Approximate token count, weighting numeric content properly."""
    if not text:
        return 0
    numbers = _NUMBER_RE.findall(text)
    numeric_chars = sum(len(n) for n in numbers)
    prose_chars = max(0, len(text) - numeric_chars)
    raw = len(numbers) * TOKENS_PER_NUMBER + prose_chars / CHARS_PER_PROSE_TOKEN
    return int(raw * TOKENISER_CALIBRATION)


@dataclass(slots=True)
class BudgetReport:
    """Whether a prompt is likely to fit, and what to do if it will not."""

    prompt_tokens: int
    context_window: int | None
    completion_reserve: int
    fits: bool
    utilisation: float | None
    breakdown: dict[str, int]
    advice: list[str]

    def summary(self) -> str:
        if self.context_window is None:
            return f"~{self.prompt_tokens} prompt tokens (context window unknown)."
        return (
            f"~{self.prompt_tokens} prompt tokens of {self.context_window} available "
            f"({self.utilisation:.0%} used, {self.completion_reserve} reserved for the reply)."
        )


def check(
    *,
    system_prompt: str,
    technical_context: str,
    dynamic_prompt: str,
    emg_context: str = "",
    image_context: str = "",
    context_window: int | None,
    completion_reserve: int = DEFAULT_COMPLETION_RESERVE,
) -> BudgetReport:
    """Estimate the prompt and compare it against the runtime's context window.

    ``context_window`` is what the model was *loaded* with, which is often far
    smaller than the architecture supports — LM Studio defaults well below the
    maximum, and that is the number that decides whether the request succeeds.

    **This counts text only.** The picture also occupies context, at a rate that
    depends on the vision encoder and the resolution the runtime rescales to,
    and no formula here would be right for more than one model. So the estimate
    is a floor, not a bound: a prompt reported as fitting with little room to
    spare may still be rejected. It is reported as a floor rather than padded
    with a guess, because a padded figure looks like a measurement.
    """
    breakdown = {
        "system_prompt": estimate_tokens(system_prompt),
        "technical_context": estimate_tokens(technical_context),
        "emg_context": estimate_tokens(emg_context),
        "image_context": estimate_tokens(image_context),
        "dynamic_prompt": estimate_tokens(dynamic_prompt),
    }
    total = sum(breakdown.values())

    if context_window is None:
        return BudgetReport(total, None, completion_reserve, True, None, breakdown, [])

    available = max(0, context_window - completion_reserve)
    fits = total <= available
    advice: list[str] = []

    if not fits:
        over = total - available
        # Round up to the next power of two: that is how runtimes present the
        # setting, so naming an exact figure would still need translating.
        target = 1 << (total + completion_reserve - 1).bit_length()
        advice.append(
            f"The prompt is about {over} tokens over budget. In LM Studio, "
            f"raise the loaded model's context length to {target} "
            f"(needs at least {total + completion_reserve})."
        )

        # Every block is now frozen text of a known, small size: the feature
        # table is eight rows whatever the recording's length, so nothing here
        # grows with the data and there is no row count to cut. If the text does
        # not fit, the context is simply too small — which is worth saying,
        # because the previous advice ("cap the rows sent") no longer refers to
        # anything the researcher can set.
        advice.append(
            "Every block is fixed-size text, so no setting in the lab will "
            "shrink it. The context length is the only lever."
        )

        if completion_reserve > 1_024:
            advice.append(
                f"{completion_reserve} tokens are reserved for the reply. The "
                "response is a small JSON object; lowering Max tokens frees that "
                "budget for the prompt."
            )

        if breakdown["technical_context"] > 4_000:
            advice.append(
                "The technical context is unusually large — check whether a "
                "custom version re-embedded the full output schema, which the "
                "structured-output request already enforces."
            )

    return BudgetReport(
        prompt_tokens=total,
        context_window=context_window,
        completion_reserve=completion_reserve,
        fits=fits,
        utilisation=total / context_window if context_window else None,
        breakdown=breakdown,
        advice=advice,
    )
