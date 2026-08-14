"""Deterministic temporal semantic serialization for sEMG and encoders."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.schemas.emg import EmgWindow
from app.schemas.multimodal import (
    MechanicalTelemetry,
    MultimodalSemanticState,
    SemanticActuatorState,
    SemanticBand,
    SemanticEmgState,
)


def _rms(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values) / len(values)) if values else 0.0


def _level(value: float) -> str:
    if value < 0.15:
        return "rest"
    if value < 0.40:
        return "low"
    if value < 0.70:
        return "medium"
    return "high"


def _trend(values: list[float]) -> str:
    if len(values) < 2:
        return "stable"
    delta = values[-1] - values[0]
    if delta > 0.08:
        return "rising"
    if delta < -0.08:
        return "falling"
    return "stable"


def serialize_multimodal_state(
    window: EmgWindow,
    telemetry: MechanicalTelemetry | None = None,
    *,
    mvc_by_channel: list[float] | None = None,
    analysis_window_ms: int = 200,
    hop_ms: int = 100,
    now: datetime | None = None,
) -> MultimodalSemanticState:
    """Convert raw streams into a compact, calibrated temporal description.

    MVC values are per-channel RMS references.  When no calibration is
    supplied, the observed peak RMS is used only as a session-relative fallback
    and the resulting state should not be compared across subjects.
    """
    rate = window.sample_rate_hz
    width = max(4, round(rate * analysis_window_ms / 1000))
    hop = max(1, round(rate * hop_ms / 1000))
    starts = list(range(0, max(1, len(window.samples) - width + 1), hop)) or [0]
    chunks = [window.samples[start:start + width] for start in starts]
    chunks = [chunk for chunk in chunks if chunk]

    channel_series: list[list[float]] = [[] for _ in range(8)]
    for chunk in chunks:
        for channel in range(8):
            channel_series[channel].append(_rms([row[channel] for row in chunk]))

    references = list(mvc_by_channel or [])
    if len(references) != 8:
        references = [max(series, default=1.0) or 1.0 for series in channel_series]
    normalized = [
        [min(1.0, max(0.0, value / max(reference, 1e-9))) for value in series]
        for series, reference in zip(channel_series, references, strict=True)
    ]
    flexor = [sum(values[i] for values in normalized[:4]) / 4 for i in range(len(chunks))]
    extensor = [sum(values[i] for values in normalized[4:7]) / 3 for i in range(len(chunks))]
    co = [min(flexor[i], extensor[i]) for i in range(len(chunks))]

    flex = flexor[-1] if flexor else 0.0
    ext = extensor[-1] if extensor else 0.0
    coc = co[-1] if co else 0.0
    difference = flex - ext
    if coc >= 0.40:
        intent = "uncertain"
    elif difference >= 0.15:
        intent = "close"
    elif difference <= -0.15:
        intent = "open"
    else:
        intent = "uncertain"
    confidence = min(1.0, abs(difference))

    labels = [_level(value) for value in (flexor if intent == "close" else extensor)]
    stable_windows = 1
    for label in reversed(labels[:-1]):
        if label != labels[-1]:
            break
        stable_windows += 1

    emg = SemanticEmgState(
        window_ms=analysis_window_ms,
        hop_ms=hop_ms,
        windows_analysed=len(chunks),
        flexor=SemanticBand(level=_level(flex), value=round(flex, 4), trend=_trend(flexor)),
        extensor=SemanticBand(level=_level(ext), value=round(ext, 4), trend=_trend(extensor)),
        co_contraction=SemanticBand(level=_level(coc), value=round(coc, 4), trend=_trend(co)),
        intent_candidate=intent,
        detected_pattern_hint=(
            "co_contraction" if coc >= 0.40 else
            "hand_open" if intent == "open" else
            "rest" if max(flex, ext) < 0.15 else "unknown"
        ),
        control_recommendation="no_action" if intent == "uncertain" else "infer_gesture",
        confidence=round(confidence, 4),
        stable_for_ms=analysis_window_ms + max(0, stable_windows - 1) * hop_ms,
    )

    clock = now or datetime.now(timezone.utc)
    mechanics: list[SemanticActuatorState] = []
    conflicts: list[str] = []
    for encoder in telemetry.actuators if telemetry else []:
        position = (encoder.position - encoder.minimum) / (encoder.maximum - encoder.minimum)
        position = min(1.0, max(0.0, position))
        age_ms = max(0.0, (clock - encoder.captured_at).total_seconds() * 1000)
        stale = age_ms > telemetry.stale_after_ms
        direction = "closing" if encoder.velocity > 0 else "opening" if encoder.velocity < 0 else "stationary"
        stalled = (
            telemetry.stall_velocity_threshold > 0
            and abs(encoder.velocity) <= telemetry.stall_velocity_threshold
            and intent in {"open", "close"}
            and not (intent == "open" and position <= 0.05)
            and not (intent == "close" and position >= 0.95)
        )
        mechanics.append(SemanticActuatorState(
            actuator=encoder.actuator, position_normalized=round(position, 4),
            direction=direction, velocity=encoder.velocity,
            near_open_limit=position <= 0.05, near_closed_limit=position >= 0.95,
            stalled=stalled, stale=stale,
        ))
        if stale:
            conflicts.append(f"{encoder.actuator}:stale_telemetry")
        if stalled:
            conflicts.append(f"{encoder.actuator}:possible_stall")
        if intent == "close" and position >= 0.95:
            conflicts.append(f"{encoder.actuator}:close_at_closed_limit")
        if intent == "open" and position <= 0.05:
            conflicts.append(f"{encoder.actuator}:open_at_open_limit")
        if intent == "close" and direction == "opening":
            conflicts.append(f"{encoder.actuator}:direction_opposes_intent")
        if intent == "open" and direction == "closing":
            conflicts.append(f"{encoder.actuator}:direction_opposes_intent")

    return MultimodalSemanticState(
        emg=emg, mechanics=mechanics, conflicts=conflicts,
        action_allowed=not conflicts and intent != "uncertain",
    )
