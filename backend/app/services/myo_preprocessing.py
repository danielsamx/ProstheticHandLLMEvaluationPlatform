"""Deterministic preprocessing for eight-channel Myo EMG windows."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, iirnotch


def preprocess(samples: list[list[float]], *, sample_rate_hz: int,
               channel_order: list[int] | None = None,
               remove_dc: bool = True, notch_hz: float | None = 50.0,
               bandpass_low_hz: float | None = 20.0,
               bandpass_high_hz: float | None = 90.0,
               rectify: bool = False, envelope_ms: int | None = None,
               normalisation: str = "none",
               calibration_scale: list[float] | None = None) -> tuple[list[list[float]], dict]:
    data = np.asarray(samples, dtype=float)
    if data.ndim != 2 or data.shape[1] != 8:
        raise ValueError("Myo data must be an N x 8 matrix.")
    order = channel_order or list(range(8))
    if sorted(order) != list(range(8)):
        raise ValueError("channel_order must be a permutation of 0..7.")
    data = data[:, order]
    if calibration_scale:
        if len(calibration_scale) != 8 or any(v <= 0 for v in calibration_scale):
            raise ValueError("calibration_scale must contain eight positive values.")
        data = data / np.asarray(calibration_scale)
    if remove_dc:
        data = data - data.mean(axis=0, keepdims=True)
    nyquist = sample_rate_hz / 2
    if notch_hz and notch_hz < nyquist and len(data) > 24:
        b, a = iirnotch(notch_hz / nyquist, 30)
        data = filtfilt(b, a, data, axis=0)
    high = min(bandpass_high_hz or nyquist * .95, nyquist * .95)
    low = bandpass_low_hz or 0
    if 0 < low < high and len(data) > 24:
        b, a = butter(4, [low / nyquist, high / nyquist], btype="band")
        data = filtfilt(b, a, data, axis=0)
    if rectify:
        data = np.abs(data)
    if envelope_ms:
        width = max(1, round(sample_rate_hz * envelope_ms / 1000))
        kernel = np.ones(width) / width
        data = np.stack([np.convolve(data[:, i], kernel, mode="same") for i in range(8)], axis=1)
    if normalisation == "zscore":
        std = data.std(axis=0)
        std[std == 0] = 1
        data = (data - data.mean(axis=0)) / std
    elif normalisation == "max_abs":
        scale = np.max(np.abs(data), axis=0)
        scale[scale == 0] = 1
        data = data / scale
    elif normalisation != "none":
        raise ValueError("normalisation must be none, zscore or max_abs.")
    metadata = {
        "pipeline_version": "myo-v1", "channel_order": order,
        "remove_dc": remove_dc, "notch_hz": notch_hz,
        "bandpass_hz": [low, high], "rectified": rectify,
        "envelope_ms": envelope_ms, "normalisation": normalisation,
        "raw_peak": float(np.max(np.abs(samples))),
        "processed_peak": float(np.max(np.abs(data))),
    }
    return data.tolist(), metadata
