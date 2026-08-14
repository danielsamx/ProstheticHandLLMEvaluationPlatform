"""Typed multimodal state supplied to the decision model.

Raw sensor streams remain in their acquisition records.  These contracts carry
the compact, timestamped mechanical evidence required to decide whether a
biological intention is compatible with the hand's current physical state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EncoderTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actuator: str = Field(min_length=1, max_length=32)
    position: float
    minimum: float
    maximum: float
    velocity: float = 0.0
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def valid_range(self) -> "EncoderTelemetry":
        if self.maximum <= self.minimum:
            raise ValueError("Encoder maximum must be greater than minimum.")
        return self


class MechanicalTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actuators: list[EncoderTelemetry] = Field(default_factory=list, max_length=16)
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stale_after_ms: int = Field(default=500, ge=50, le=10_000)
    stall_velocity_threshold: float = Field(default=0.01, ge=0.0)


class SemanticBand(BaseModel):
    level: Literal["rest", "low", "medium", "high"]
    value: float = Field(ge=0.0, le=1.0)
    trend: Literal["falling", "stable", "rising"]


class SemanticEmgState(BaseModel):
    window_ms: int
    hop_ms: int
    windows_analysed: int
    flexor: SemanticBand
    extensor: SemanticBand
    co_contraction: SemanticBand
    intent_candidate: Literal["open", "close", "uncertain"]
    detected_pattern_hint: Literal["rest", "hand_open", "co_contraction", "unknown"]
    control_recommendation: Literal["infer_gesture", "no_action", "stop"]
    confidence: float = Field(ge=0.0, le=1.0)
    stable_for_ms: int = Field(ge=0)


class SemanticActuatorState(BaseModel):
    actuator: str
    position_normalized: float = Field(ge=0.0, le=1.0)
    direction: Literal["opening", "stationary", "closing"]
    velocity: float
    near_open_limit: bool
    near_closed_limit: bool
    stalled: bool
    stale: bool


class MultimodalSemanticState(BaseModel):
    emg: SemanticEmgState
    mechanics: list[SemanticActuatorState] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    action_allowed: bool = True
