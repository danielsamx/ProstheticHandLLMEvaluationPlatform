from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.emg import EmgWindow


class MyoPreprocessIn(BaseModel):
    samples: list[list[float]]
    sample_rate_hz: int = Field(default=200, ge=100, le=2000)
    channel_order: list[int] = Field(default_factory=lambda: list(range(8)), min_length=8, max_length=8)
    calibration_scale: list[float] | None = None
    remove_dc: bool = True
    notch_hz: float | None = Field(default=50, gt=0)
    bandpass_low_hz: float | None = Field(default=20, gt=0)
    bandpass_high_hz: float | None = Field(default=90, gt=0)
    rectify: bool = False
    envelope_ms: int | None = Field(default=None, ge=5, le=500)
    normalisation: str = Field(default="max_abs", pattern="^(none|zscore|max_abs)$")
    subject_ref: str | None = None
    ground_truth_gesture: str | None = None


class MyoPreprocessOut(BaseModel):
    raw_window: EmgWindow
    processed_window: EmgWindow
    metadata: dict
