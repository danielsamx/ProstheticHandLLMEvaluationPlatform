from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GestureFeedbackIn(BaseModel):
    is_correct: bool
    score: int | None = Field(default=None, ge=0, le=100)
    expected_gesture: str | None = Field(default=None, max_length=64)
    observed_gesture: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)
    source: str = Field(default="human", pattern="^(human|potentiometer|fsr|vision|combined)$")
    sensor_snapshot: dict = Field(default_factory=dict)
    auto_retry: bool = False
    max_attempts: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def require_correction_signal(self):
        if not self.is_correct and not any((self.expected_gesture, self.notes, self.sensor_snapshot)):
            raise ValueError("Incorrect gestures require an expected gesture, notes or sensor evidence.")
        return self


class GestureFeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    execution_id: uuid.UUID
    evaluator_email: str | None
    source: str
    is_correct: bool
    score: int | None
    expected_gesture: str | None
    observed_gesture: str | None
    notes: str | None
    sensor_snapshot: dict
    correction_attempt: int
    correction_execution_id: uuid.UUID | None
    created_at: datetime


class FeedbackResult(BaseModel):
    feedback: GestureFeedbackOut
    correction_execution_id: uuid.UUID | None = None
    requires_confirmation: bool = True
