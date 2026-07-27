"""Feature extraction from a raw EMG sample matrix.

Input is an ``N x 8`` matrix: one row per time step, one column per electrode,
amplitudes normalised to [-1.0, 1.0].  The five descriptors computed here are
the standard time-domain feature set for myoelectric control (Hudgins et al.),
and they are handed to the model *alongside* the raw matrix so an experiment can
measure which representation a given model actually relies on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

#: Amplitudes below this are treated as baseline noise for ZC/SSC counting.
#: Without a deadband, sensor noise around zero inflates both counts by an order
#: of magnitude and the features stop discriminating anything.
ZC_THRESHOLD: float = 0.01
SSC_THRESHOLD: float = 0.01


def column(matrix: Sequence[Sequence[float]], index: int) -> list[float]:
    """Extract one electrode's time series from an N x 8 matrix."""
    return [row[index] for row in matrix]


def rms(signal: Sequence[float]) -> float:
    """Root mean square amplitude - correlates with contraction force."""
    if not signal:
        return 0.0
    return math.sqrt(sum(x * x for x in signal) / len(signal))


def mav(signal: Sequence[float]) -> float:
    """Mean absolute value - cheaper amplitude estimate, less noise sensitive."""
    if not signal:
        return 0.0
    return sum(abs(x) for x in signal) / len(signal)


def zero_crossings(signal: Sequence[float], threshold: float = ZC_THRESHOLD) -> int:
    """Sign changes above a deadband - a proxy for mean frequency."""
    count = 0
    for previous, current in zip(signal, signal[1:]):
        if previous * current < 0 and abs(previous - current) >= threshold:
            count += 1
    return count


def slope_sign_changes(signal: Sequence[float], threshold: float = SSC_THRESHOLD) -> int:
    """Direction reversals of the first difference - frequency content."""
    count = 0
    for a, b, c in zip(signal, signal[1:], signal[2:]):
        if (b - a) * (b - c) > 0 and (abs(b - a) >= threshold or abs(b - c) >= threshold):
            count += 1
    return count


def waveform_length(signal: Sequence[float]) -> float:
    """Cumulative path length, normalised by sample count.

    Combines amplitude and frequency into one number; often the single most
    informative descriptor for gesture classification.
    """
    if len(signal) < 2:
        return 0.0
    total = sum(abs(b - a) for a, b in zip(signal, signal[1:]))
    return total / (len(signal) - 1)


def variance(signal: Sequence[float]) -> float:
    if len(signal) < 2:
        return 0.0
    mean = sum(signal) / len(signal)
    return sum((x - mean) ** 2 for x in signal) / (len(signal) - 1)


def extract_channel_features(signal: Sequence[float]) -> dict[str, float | int]:
    """Full descriptor set for a single electrode."""
    return {
        "rms": round(rms(signal), 5),
        "mav": round(mav(signal), 5),
        "zc": zero_crossings(signal),
        "ssc": slope_sign_changes(signal),
        "wl": round(waveform_length(signal), 5),
        "min": round(min(signal), 5) if signal else 0.0,
        "max": round(max(signal), 5) if signal else 0.0,
        "variance": round(variance(signal), 6),
    }


def extract_matrix_features(
    matrix: Sequence[Sequence[float]], labels: Sequence[str]
) -> list[dict[str, float | int | str]]:
    """Per-channel descriptors for an N x 8 matrix, in column order."""
    if not matrix:
        return [{"label": label, "rms": 0.0, "mav": 0.0, "zc": 0, "ssc": 0,
                 "wl": 0.0, "min": 0.0, "max": 0.0, "variance": 0.0} for label in labels]

    features: list[dict[str, float | int | str]] = []
    for index, label in enumerate(labels):
        signal = column(matrix, index)
        features.append({"label": label, **extract_channel_features(signal)})
    return features


def downsample(
    matrix: Sequence[Sequence[float]], max_rows: int
) -> tuple[list[list[float]], int]:
    """Decimate a long window for prompt rendering.

    Returns ``(rows, factor)``.  Uniform stride rather than averaging: averaging
    would smooth away the high-frequency content that ZC and SSC measure, and
    the model would be shown a signal whose features do not match the summary
    printed beside it.
    """
    total = len(matrix)
    if total <= max_rows or max_rows <= 0:
        return [list(row) for row in matrix], 1

    factor = math.ceil(total / max_rows)
    return [list(matrix[i]) for i in range(0, total, factor)], factor


# ═══════════════════════════════════════════════════════════════════════════
# Amplitude normalisation
# ═══════════════════════════════════════════════════════════════════════════


class NormalisationError(ValueError):
    """The requested normalisation cannot produce values inside [-1, 1]."""


class NormalisationMode(str, Enum):
    """How raw acquisition values are mapped onto [-1.0, 1.0]."""

    NONE = "none"              # already normalised; reject anything outside range
    FULL_SCALE = "full_scale"  # divide by a declared converter full scale
    PEAK = "peak"              # divide by this window's own largest magnitude


@dataclass(slots=True)
class NormalisationReport:
    """What was done to the amplitudes, and whether it is safe to compare."""

    mode: NormalisationMode
    observed_peak: float
    divisor: float
    inferred_full_scale: bool
    warnings: list[str]


def _next_power_of_two(value: float) -> int:
    """Smallest power of two at or above ``value`` (minimum 1)."""
    if value <= 1:
        return 1
    return 1 << (math.ceil(math.log2(value)))


def normalise_matrix(
    matrix: list[list[float]],
    mode: NormalisationMode = NormalisationMode.FULL_SCALE,
    full_scale: float | None = None,
) -> tuple[list[list[float]], NormalisationReport]:
    """Map acquisition units onto the normalised amplitude range.

    The choice of divisor is not cosmetic. ``PEAK`` rescales each window by its
    own maximum, which means a resting window and a maximal grasp both come out
    peaking at 1.0 — the amplitude information that distinguishes them is
    destroyed. Since this platform exists to compare activation levels across
    windows and across models, ``FULL_SCALE`` is the default and ``PEAK`` is
    reported as comparability-breaking whenever it is used.
    """
    peak = max((abs(v) for row in matrix for v in row), default=0.0)
    warnings: list[str] = []
    inferred = False

    if mode is NormalisationMode.NONE:
        divisor = 1.0
    elif mode is NormalisationMode.PEAK:
        divisor = peak or 1.0
        warnings.append(
            "Peak normalisation rescales this window by its own maximum, so its "
            "amplitudes are NOT comparable with windows normalised differently. "
            "Use a declared full scale for any experiment that compares "
            "activation levels."
        )
    else:
        if full_scale is None or full_scale <= 0:
            divisor = float(_next_power_of_two(peak))
            inferred = True
            warnings.append(
                f"Full scale was inferred from this window as {divisor:g} (peak "
                f"{peak:g}). Declare the converter's actual full scale to keep "
                "amplitudes comparable across recordings."
            )
        else:
            divisor = float(full_scale)

    if divisor != 1.0:
        matrix = [[v / divisor for v in row] for row in matrix]

    out_of_range = [v for row in matrix for v in row if abs(v) > 1.0]
    if out_of_range:
        largest = max(abs(v) for v in out_of_range)
        if mode is NormalisationMode.NONE:
            raise NormalisationError(
                f"{len(out_of_range)} value(s) fall outside [-1.0, 1.0] (largest "
                f"magnitude {peak:g}). These look like raw converter counts — "
                "choose a normalisation mode."
            )
        raise NormalisationError(
            f"After dividing by {divisor:g}, {len(out_of_range)} value(s) still "
            f"exceed 1.0 (largest {largest:g}). The declared full scale is too "
            f"small for this data; the observed peak is {peak:g}."
        )

    return matrix, NormalisationReport(mode, peak, divisor, inferred, warnings)
