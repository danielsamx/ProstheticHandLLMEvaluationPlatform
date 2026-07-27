"""EMG persistence, matrix parsing and synthetic signal generation."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.hand_spec import EMG_CHANNEL_COUNT, EMG_CHANNELS
from app.services.emg_features import (
    NormalisationError,
    NormalisationMode,
    NormalisationReport,
    normalise_matrix,
)
from app.models.emg import EmgWindowRecord
from app.schemas.emg import EmgSourceMode, EmgWindow

DEFAULT_SYNTHETIC_SAMPLES: int = 200

__all__ = [
    "MatrixParseError", "NormalisationMode", "NormalisationReport",
    "normalise_matrix", "parse_matrix_text", "matrix_to_csv",
    "synthesise_window", "blank_window", "persist_window", "record_to_window",
    "window_checksum", "SYNTHETIC_GESTURES",
]


# ═════════════════════════════════════════════════════════════════════════════
# Persistence
# ═════════════════════════════════════════════════════════════════════════════


def window_checksum(window: EmgWindow) -> str:
    """Content address of the physiological stimulus.

    Hashes the matrix and sampling rate only - not timestamps or provenance -
    so replaying the identical signal across models is provable rather than
    assumed.
    """
    quantised = [[round(value, 6) for value in row] for row in window.samples]
    canonical = json.dumps(
        {"samples": quantised, "fs": window.sample_rate_hz},
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def persist_window(
    session: AsyncSession,
    window: EmgWindow,
    *,
    subject_ref: str | None = None,
    session_id: str | None = None,
    sequence: int | None = None,
) -> EmgWindowRecord:
    """Store one window. Windows are append-only - never updated in place."""
    record = EmgWindowRecord(
        source_mode=window.source_mode.value,
        sample_rate_hz=window.sample_rate_hz,
        samples=window.samples,
        sample_count=window.sample_count,
        window_ms=window.window_ms,
        features=window.features_dict(),
        mean_rms=round(window.total_activation, 6),
        ground_truth_gesture=window.ground_truth_gesture,
        subject_ref=subject_ref,
        session_id=session_id,
        sequence=sequence,
        captured_at=window.captured_at or datetime.now(timezone.utc),
        checksum=window_checksum(window),
        notes=window.notes,
    )
    session.add(record)
    await session.flush()
    return record


def record_to_window(record: EmgWindowRecord) -> EmgWindow:
    """Rehydrate a stored window (used when replaying an experiment)."""
    return EmgWindow(
        samples=record.samples,
        source_mode=EmgSourceMode(record.source_mode),
        sample_rate_hz=record.sample_rate_hz,
        captured_at=record.captured_at,
        ground_truth_gesture=record.ground_truth_gesture,
        notes=record.notes,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Matrix parsing (CSV / TSV / JSON paste)
# ═════════════════════════════════════════════════════════════════════════════

_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

#: A line made up entirely of identifier-like tokens and separators is a header.
#: This has to be checked BEFORE extracting numbers: "CH1,CH2,...,CH8" would
#: otherwise parse as the perfectly-shaped data row [1, 2, ..., 8].
_HEADER_RE = re.compile(r'^[\s,;\t]*(?:"?[A-Za-z_][A-Za-z0-9_]*"?[\s,;\t]*)+$')


class MatrixParseError(ValueError):
    """The pasted text could not be read as an N x 8 matrix."""


#: Normalisation failures are a parse failure from the caller's point of view.
MatrixError = (MatrixParseError, NormalisationError)


def parse_matrix_text(text: str) -> list[list[float]]:
    """Read an N x 8 matrix from CSV, TSV, whitespace or JSON text.

    Values are returned in whatever units the file used; call
    :func:`normalise_matrix` to map them onto [-1.0, 1.0].

    Deliberately permissive about delimiters and bracket noise, because the
    realistic input is a copy-paste out of MATLAB, NumPy or a spreadsheet - but
    strict about shape, because a silently transposed matrix would corrupt every
    downstream feature.
    """
    stripped = text.strip()
    if not stripped:
        raise MatrixParseError("No data supplied.")

    matrix: list[list[float]] | None = None

    # JSON first: unambiguous when it parses.
    if stripped[0] in "[{":
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            payload = payload.get("samples") or payload.get("matrix") or payload.get("data")
        if isinstance(payload, list) and payload and isinstance(payload[0], list):
            matrix = [[float(v) for v in row] for row in payload]

    # Otherwise: one row per line, numbers extracted by regex.
    if matrix is None:
        rows: list[list[float]] = []
        for index, line in enumerate(stripped.splitlines()):
            cleaned = line.strip().strip("[](){},;")
            if not cleaned:
                continue
            if _HEADER_RE.match(cleaned):
                continue  # column labels
            values = [float(m.group()) for m in _NUMBER_RE.finditer(cleaned)]
            if not values:
                raise MatrixParseError(f"Line {index + 1} contains no numbers: {line!r}")
            rows.append(values)
        matrix = rows

    if not matrix:
        raise MatrixParseError("No numeric rows found.")

    widths = {len(row) for row in matrix}
    if widths != {EMG_CHANNEL_COUNT}:
        # The single most likely mistake is a transposed matrix; say so plainly.
        if len(matrix) == EMG_CHANNEL_COUNT and len(widths) == 1:
            raise MatrixParseError(
                f"Got {EMG_CHANNEL_COUNT} rows of {widths.pop()} columns. This looks "
                "transposed: the expected layout is one row per time step and 8 "
                "columns (CH1..CH8). Transpose it and retry."
            )
        raise MatrixParseError(
            f"Every row must have exactly {EMG_CHANNEL_COUNT} columns "
            f"(CH1..CH{EMG_CHANNEL_COUNT}); found row widths {sorted(widths)}."
        )

    return matrix


def matrix_to_csv(matrix: list[list[float]], precision: int = 4) -> str:
    """Serialise a matrix for export or display.

    Exported with the platform's CH1..CH8 labels. Acquisition tools that emit
    zero-indexed CH0..CH7 headers are read back correctly: the header line is
    skipped by shape, not by matching specific labels.
    """
    header = ",".join(EMG_CHANNELS)
    rows = [",".join(f"{v:.{precision}f}" for v in row) for row in matrix]
    return "\n".join([header, *rows])


# ═════════════════════════════════════════════════════════════════════════════
# Synthetic generation (labelled stimuli for automatic accuracy scoring)
# ═════════════════════════════════════════════════════════════════════════════

#: Target RMS per channel for each gesture, over CH1..CH8.
#: CH1-CH4 volar/flexor, CH5-CH7 dorsal/extensor, CH8 brachioradialis.
#: Values are RMS, not peak. Surface EMG has a crest factor around 3-4, so an
#: RMS of 0.30 already puts occasional peaks near full scale - which is what a
#: maximal contraction looks like on a normalised channel.
_TEMPLATES: dict[str, tuple[float, ...]] = {
    "rest":             (0.022, 0.018, 0.026, 0.022, 0.022, 0.018, 0.022, 0.028),
    "hand_open":        (0.055, 0.050, 0.045, 0.055, 0.300, 0.275, 0.270, 0.120),
    "power_grasp":      (0.330, 0.308, 0.319, 0.292, 0.055, 0.050, 0.060, 0.165),
    "precision_pinch":  (0.215, 0.242, 0.116, 0.187, 0.099, 0.077, 0.072, 0.116),
    "point":            (0.116, 0.110, 0.231, 0.138, 0.215, 0.116, 0.099, 0.110),
    "thumbs_up":        (0.242, 0.138, 0.259, 0.226, 0.116, 0.171, 0.088, 0.138),
    "ok_sign":          (0.187, 0.226, 0.099, 0.171, 0.132, 0.099, 0.088, 0.116),
    "co_contraction":   (0.308, 0.297, 0.302, 0.286, 0.308, 0.291, 0.286, 0.231),
}

SYNTHETIC_GESTURES: tuple[str, ...] = tuple(_TEMPLATES)


def _band_limited_noise(
    length: int, rng: random.Random, sample_rate_hz: int
) -> list[float]:
    """Generate one channel of EMG-like signal.

    Surface EMG is well modelled as band-limited Gaussian noise (the
    interference pattern of many motor unit action potentials). A one-pole
    low-pass followed by a first difference gives a spectrum peaking in the
    20-150 Hz band without pulling in a DSP dependency.
    """
    # One-pole coefficient placing the corner near 150 Hz.
    alpha = math.exp(-2.0 * math.pi * 150.0 / sample_rate_hz)

    white = [rng.gauss(0.0, 1.0) for _ in range(length + 2)]
    low: list[float] = []
    state = 0.0
    for value in white:
        state = alpha * state + (1.0 - alpha) * value
        low.append(state)

    # First difference removes DC and the sub-20 Hz motion artefact band.
    band = [low[i] - low[i - 1] for i in range(1, len(low))]
    return band[:length]


#: Amplitude above which the front end starts compressing rather than clipping.
_LIMIT_KNEE: float = 0.85


def _soft_limit(value: float) -> float:
    """Compress the tail instead of clipping it.

    A hard clip flattens every peak onto exactly +/-1.0, which destroys the
    crest factor and inflates the zero-crossing count. Real instrumentation
    amplifiers compress smoothly into saturation, so the tail is folded with a
    tanh above the knee and left untouched below it.
    """
    magnitude = abs(value)
    if magnitude <= _LIMIT_KNEE:
        return value
    sign = 1.0 if value >= 0 else -1.0
    excess = magnitude - _LIMIT_KNEE
    return sign * (_LIMIT_KNEE + (1.0 - _LIMIT_KNEE) * math.tanh(excess / (1.0 - _LIMIT_KNEE)))


def _scale_to_rms(signal: list[float], target_rms: float) -> list[float]:
    current = math.sqrt(sum(x * x for x in signal) / len(signal)) if signal else 0.0
    if current == 0.0:
        return [0.0] * len(signal)
    gain = target_rms / current
    return [_soft_limit(x * gain) for x in signal]


def synthesise_window(
    gesture: str,
    *,
    noise: float = 0.12,
    seed: int | None = None,
    samples: int = DEFAULT_SYNTHETIC_SAMPLES,
    sample_rate_hz: int = 1_000,
) -> EmgWindow:
    """Generate a labelled raw EMG matrix for a known target gesture.

    ``noise`` is a relative standard deviation on each channel's target RMS,
    so the rest/active contrast survives regardless of the absolute level.

    ``seed`` makes the stimulus reproducible, which matters: the same synthetic
    window must be replayable across every model under test.
    """
    key = gesture.strip().lower()
    if key not in _TEMPLATES:
        raise ValueError(f"Unknown synthetic gesture {gesture!r}. Valid: {SYNTHETIC_GESTURES}")

    rng = random.Random(seed)
    template = _TEMPLATES[key]

    channels: list[list[float]] = []
    for base in template:
        # Multiplicative, not additive: an absolute jitter of 0.05 would swamp a
        # rest template whose channels sit at 0.02, and "rest" would stop being
        # distinguishable from light activity.
        target = max(0.0, min(1.0, base * (1.0 + rng.gauss(0.0, noise))))
        raw = _band_limited_noise(samples, rng, sample_rate_hz)
        channels.append(_scale_to_rms(raw, target))

    # Transpose channel-major into the N x 8 row-major layout.
    matrix = [
        [channels[c][n] for c in range(EMG_CHANNEL_COUNT)] for n in range(samples)
    ]

    return EmgWindow(
        samples=matrix,
        source_mode=EmgSourceMode.SYNTHETIC,
        sample_rate_hz=sample_rate_hz,
        ground_truth_gesture=key,
        notes=f"Synthetic stimulus (seed={seed}, noise={noise}, {samples} samples).",
    )


def blank_window(
    source_mode: EmgSourceMode = EmgSourceMode.MANUAL,
    samples: int = 64,
    sample_rate_hz: int = 1_000,
) -> EmgWindow:
    """An all-zero matrix - the UI's initial state."""
    return EmgWindow(
        samples=[[0.0] * EMG_CHANNEL_COUNT for _ in range(samples)],
        source_mode=source_mode,
        sample_rate_hz=sample_rate_hz,
    )
