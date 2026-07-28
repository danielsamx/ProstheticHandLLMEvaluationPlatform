"""Prompt size estimation and context-budget checks.

A prompt that overflows the runtime's context window fails at the provider with
a message the researcher cannot act on without reading the server log. Checking
before the request costs nothing and turns it into an explicit, fixable warning.

Estimation is deliberately conservative. Character-count heuristics are badly
wrong for this content: an EMG matrix is almost entirely numbers, and a signed
three-decimal value like ``-0.004`` costs three to four tokens across roughly
six characters — where prose costs one token per four. Dividing by four
under-counted a real prompt by more than half.
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
    context_window: int | None,
    completion_reserve: int = DEFAULT_COMPLETION_RESERVE,
    matrix_rows: int | None = None,
) -> BudgetReport:
    """Estimate the prompt and compare it against the runtime's context window.

    ``context_window`` is what the model was *loaded* with, which is often far
    smaller than the architecture supports — LM Studio defaults well below the
    maximum, and that is the number that decides whether the request succeeds.
    """
    breakdown = {
        "system_prompt": estimate_tokens(system_prompt),
        "technical_context": estimate_tokens(technical_context),
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

        # The matrix is sent whole by default, so on any real recording it is
        # the dominant block and the only one worth talking about. The advice
        # names a row count rather than a token count: rows are what the
        # researcher can actually set.
        largest = max(breakdown, key=breakdown.get)
        if largest == "dynamic_prompt":
            from app.prompts.dynamic_prompt import rows_that_fit

            fixed = breakdown["system_prompt"] + breakdown["technical_context"]
            affordable = rows_that_fit(available - fixed)
            detail = f" ({matrix_rows} rows sent)" if matrix_rows else ""
            advice.append(
                f"The EMG matrix is the largest block{detail}. This context "
                f"holds roughly {affordable} rows alongside the frozen blocks. "
                "Either cap the rows sent, raise the model's context length, or "
                "switch the dynamic block to features only — the descriptors are "
                "computed from the complete window either way, so nothing is "
                "lost by not printing every sample."
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
