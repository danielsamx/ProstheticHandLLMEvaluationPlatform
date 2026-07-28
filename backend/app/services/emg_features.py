"""Feature extraction from a raw EMG sample matrix.

Input is an ``N x 8`` matrix: one row per time step, one column per electrode,
amplitudes normalised to [-1.0, 1.0].  The five descriptors computed here are
the standard time-domain feature set for myoelectric control (Hudgins et al.),
and they are handed to the model *alongside* the raw matrix so an experiment can
measure which representation a given model actually relies on.
"""

from __future__ import annotations

import math
from typing import Sequence

#: Deadband for ZC/SSC counting, as a fraction of the channel's own RMS.
#:
#: It has to be relative. The signal now arrives in whatever units the converter
#: produces — counts, microvolts, anything — so a fixed absolute threshold would
#: either count every noise crossing on a small-amplitude channel or suppress
#: real ones on a large one. Scaling by RMS makes both features invariant to the
#: acquisition gain, which is the property that lets two recordings be compared.
ZC_THRESHOLD_RATIO: float = 0.05
SSC_THRESHOLD_RATIO: float = 0.05


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


def zero_crossings(signal: Sequence[float], threshold: float | None = None) -> int:
    """Sign changes above a deadband - a proxy for mean frequency.

    ``threshold`` defaults to a fraction of the signal's own RMS, so the count
    does not change when the acquisition gain does.
    """
    if threshold is None:
        threshold = rms(signal) * ZC_THRESHOLD_RATIO
    count = 0
    for previous, current in zip(signal, signal[1:]):
        if previous * current < 0 and abs(previous - current) >= threshold:
            count += 1
    return count


def slope_sign_changes(signal: Sequence[float], threshold: float | None = None) -> int:
    """Direction reversals of the first difference - frequency content."""
    if threshold is None:
        threshold = rms(signal) * SSC_THRESHOLD_RATIO
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
