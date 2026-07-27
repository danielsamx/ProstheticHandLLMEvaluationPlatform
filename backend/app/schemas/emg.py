"""EMG acquisition payloads.

The stimulus is a raw sample **matrix**: ``N`` rows (time steps) by 8 columns
(electrodes), amplitudes normalised to [-1.0, 1.0].  Time-domain features are
*derived* from the matrix by the backend rather than supplied by the caller, so
the descriptors the model sees can never disagree with the signal printed
beside them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from functools import cached_property
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from app.domain.hand_spec import (
    DEFAULT_EMG_SAMPLE_RATE_HZ,
    EMG_CHANNEL_COUNT,
    EMG_CHANNELS,
)
from app.services import emg_features
from app.services.emg_features import NormalisationMode

#: Guard rails on window length. A single sample carries no frequency content;
#: beyond ~8k rows the prompt stops fitting in any reasonable context window.
MIN_SAMPLES: int = 4
MAX_SAMPLES: int = 8_192

Amplitude = Annotated[float, Field(ge=-1.0, le=1.0)]

#: Output-only fields, stripped when a serialised window is submitted back.
_COMPUTED_FIELDS: frozenset[str] = frozenset({"sample_count", "window_ms", "features"})


class EmgSourceMode(str, Enum):
    """Where the window came from. Recorded with every execution so that manual
    and live runs are never silently pooled in an analysis."""

    MANUAL = "manual"        # typed or pasted into the left panel
    LIVE = "live"            # streamed from the acquisition hardware
    DATASET = "dataset"      # replayed from a stored recording
    SYNTHETIC = "synthetic"  # generated from a known ground-truth gesture


class EmgChannelFeatures(BaseModel):
    """Time-domain descriptors for one electrode, derived from the matrix."""

    model_config = ConfigDict(extra="forbid")

    label: str
    rms: float = Field(description="Root mean square amplitude.")
    mav: float = Field(description="Mean absolute value.")
    zc: int = Field(description="Zero crossings above a 0.01 deadband.")
    ssc: int = Field(description="Slope sign changes above a 0.01 deadband.")
    wl: float = Field(description="Waveform length per sample.")
    min: float
    max: float
    variance: float


class EmgWindow(BaseModel):
    """One analysis window: the raw matrix plus everything derived from it."""

    model_config = ConfigDict(extra="forbid")

    samples: list[list[Amplitude]] = Field(
        description=(
            "Raw EMG matrix. One row per time step, 8 columns in CH1..CH8 order, "
            "amplitudes normalised to [-1.0, 1.0]."
        ),
    )
    source_mode: EmgSourceMode = EmgSourceMode.MANUAL
    sample_rate_hz: int = Field(default=DEFAULT_EMG_SAMPLE_RATE_HZ, ge=100, le=20_000)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    #: Known correct answer, when the window is labelled. Enables automatic
    #: accuracy scoring without manual annotation.
    ground_truth_gesture: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=500)

    # ── Shape validation ────────────────────────────────────────────────────

    @model_validator(mode="before")
    @classmethod
    def _drop_computed(cls, data: object) -> object:
        """Let a serialised window be posted straight back.

        ``sample_count`` and ``window_ms`` are computed fields: they appear in
        every response but are not accepted as input, and ``extra="forbid"``
        would otherwise reject the model's own output. A client that fetches a
        synthetic window and submits it for execution does exactly that, so the
        keys are dropped here rather than pushed onto every caller.
        """
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in _COMPUTED_FIELDS}
        return data

    @field_validator("samples")
    @classmethod
    def _rectangular_and_bounded(cls, matrix: list[list[float]]) -> list[list[float]]:
        if len(matrix) < MIN_SAMPLES:
            raise ValueError(
                f"EMG matrix needs at least {MIN_SAMPLES} rows; {len(matrix)} given."
            )
        if len(matrix) > MAX_SAMPLES:
            raise ValueError(
                f"EMG matrix exceeds {MAX_SAMPLES} rows ({len(matrix)} given). "
                "Decimate or shorten the window."
            )
        for index, row in enumerate(matrix):
            if len(row) != EMG_CHANNEL_COUNT:
                raise ValueError(
                    f"Row {index} has {len(row)} columns; every row must have "
                    f"exactly {EMG_CHANNEL_COUNT} (CH1..CH{EMG_CHANNEL_COUNT})."
                )
        return matrix

    # ── Derived ─────────────────────────────────────────────────────────────

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def window_ms(self) -> float:
        """Window duration implied by the row count and sampling rate."""
        return round(len(self.samples) / self.sample_rate_hz * 1000.0, 3)

    @cached_property
    def features(self) -> list[EmgChannelFeatures]:
        """Per-channel descriptors, computed once per window."""
        return [
            EmgChannelFeatures(**payload)
            for payload in emg_features.extract_matrix_features(
                self.samples, EMG_CHANNELS
            )
        ]

    @property
    def channel_labels(self) -> tuple[str, ...]:
        return EMG_CHANNELS

    @property
    def total_activation(self) -> float:
        """Mean RMS across the eight electrodes."""
        values = [f.rms for f in self.features]
        return sum(values) / len(values) if values else 0.0

    @property
    def flexor_activation(self) -> float:
        """CH1-CH4: volar compartment, associated with closing."""
        return sum(f.rms for f in self.features[:4]) / 4

    @property
    def extensor_activation(self) -> float:
        """CH5-CH7: dorsal compartment, associated with opening."""
        return sum(f.rms for f in self.features[4:7]) / 3

    def features_dict(self) -> list[dict]:
        return [f.model_dump() for f in self.features]


class EmgStreamFrame(BaseModel):
    """A frame pushed over the live WebSocket channel."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    sequence: int = Field(ge=0)
    window: EmgWindow
    auto_run: bool = Field(
        default=False,
        description="When true the backend immediately launches an execution for "
        "this frame using the session's pinned configuration.",
    )


class MatrixParseRequest(BaseModel):
    """Free-text matrix paste or file import from the UI (CSV, TSV or JSON)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=16_000_000)
    sample_rate_hz: int = Field(default=DEFAULT_EMG_SAMPLE_RATE_HZ, ge=100, le=20_000)
    normalisation: NormalisationMode = Field(
        default=NormalisationMode.FULL_SCALE,
        description="'none' expects data already in [-1,1]; 'full_scale' divides "
        "by the converter's declared range; 'peak' divides by this window's own "
        "maximum, which breaks amplitude comparability between windows.",
    )
    full_scale: float | None = Field(
        default=None, gt=0,
        description="Converter full scale in acquisition units, e.g. 512 for a "
        "10-bit signed ADC. Inferred from the window when omitted.",
    )
    ground_truth_gesture: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _not_blank(self) -> "MatrixParseRequest":
        if not self.text.strip():
            raise ValueError("Matrix text is empty.")
        return self


class MatrixParseResponse(BaseModel):
    """The parsed window plus a record of what was done to its amplitudes."""

    model_config = ConfigDict(extra="forbid")

    window: EmgWindow
    normalisation: NormalisationMode
    observed_peak: float = Field(description="Largest magnitude in the source units.")
    divisor: float = Field(description="Value the source data was divided by.")
    inferred_full_scale: bool = Field(
        description="True when the divisor was guessed from this window rather "
        "than declared, which makes cross-recording comparisons unsafe."
    )
    warnings: list[str] = Field(default_factory=list)
