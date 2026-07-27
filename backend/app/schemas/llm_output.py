"""The strict JSON contract the LLM must emit.

This schema is the interface between an arbitrary language model and a physical
actuator.  It is deliberately narrow: no free text, no optional prose fields,
closed enumerations everywhere.  ``model_json_schema()`` is injected verbatim
into the technical-context prompt block so that the model sees exactly the
structure it will be validated against.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.hand_spec import (
    EMG_CHANNELS,
    Actuator,
    ControlCommand,
    Handedness,
    SAFETY,
)

ActuatorLetter = Literal["A", "B", "C", "D", "E", "F"]
GestureLetter = Literal[
    "O", "C", "P", "R", "W", "Y", "L", "M", "H", "U", "G", "S", "X", "I"
]


class ActuatorCommand(BaseModel):
    """One positional actuator command."""

    model_config = ConfigDict(extra="forbid")

    actuator: ActuatorLetter = Field(
        description="Serial command letter: A=pinky, B=ring, C=middle, D=index, "
        "E=thumb lower/rotation, F=thumb upper/flexion."
    )
    position: int = Field(
        ge=0,
        le=600,
        description="Target encoder position. Must respect the per-actuator "
        "maximum given in the technical context.",
    )
    speed_pct: Annotated[int, Field(ge=SAFETY.min_speed_pct, le=SAFETY.max_speed_pct)] = Field(
        default=SAFETY.default_speed_pct,
        description="Motion speed as a percentage of maximum motor duty cycle.",
    )

    @property
    def actuator_enum(self) -> Actuator:
        return Actuator(self.actuator)


class SafetyBlock(BaseModel):
    """The model's own safety self-assessment. Advisory only - the backend
    re-derives every field independently and never trusts these values."""

    model_config = ConfigDict(extra="forbid")

    within_limits: bool = Field(
        description="True if every commanded position lies inside the documented range."
    )
    emergency_stop: bool = Field(
        default=False,
        description="True only when the EMG pattern indicates the hand must halt immediately.",
    )
    collision_risk: bool = Field(
        default=False,
        description="True if the requested pose could drive digits into each other.",
    )


class ProstheticCommand(BaseModel):
    """Root object. The LLM must emit exactly this and nothing else."""

    model_config = ConfigDict(extra="forbid")

    hand: Literal["right", "left"] = Field(
        description="Which hand the command targets. Must echo the requested hand."
    )
    intent: Literal["gesture", "joint_positions", "stop", "no_action"] = Field(
        description="'gesture' = use a firmware preset; 'joint_positions' = drive "
        "individual actuators; 'stop' = emergency halt; 'no_action' = EMG below "
        "activation threshold, hold current pose."
    )
    gesture: GestureLetter | None = Field(
        default=None,
        description="Preset gesture letter. Required when intent='gesture' or 'stop', "
        "otherwise null.",
    )
    commands: list[ActuatorCommand] = Field(
        default_factory=list,
        max_length=len(Actuator),
        description="Individual actuator targets. Required when intent='joint_positions', "
        "otherwise an empty list.",
    )
    serial_command: str = Field(
        min_length=1,
        max_length=128,
        description="The exact ASCII line to transmit over Bluetooth SPP, e.g. "
        "'A320,D120' or 'P'. Use the literal string 'NONE' when intent='no_action'. "
        "Must be consistent with intent/gesture/commands.",
    )
    detected_pattern: str = Field(
        max_length=64,
        description="Short machine-readable label for the muscle pattern recognised, "
        "e.g. 'power_grasp', 'rest', 'lateral_pinch'. Snake case, no spaces.",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Model confidence in the EMG interpretation.",
    )
    dominant_channels: list[str] = Field(
        default_factory=list,
        max_length=len(EMG_CHANNELS),
        description="EMG channel labels that drove the decision, e.g. ['CH1','CH5'].",
    )
    estimated_duration_ms: int = Field(
        ge=0, le=SAFETY.max_move_duration_ms,
        description="Expected time for the motion to complete.",
    )
    safety: SafetyBlock

    # ── Cross-field consistency (structural only; physical limits are checked
    #    by the validation pipeline against the active limit profile) ─────────

    @model_validator(mode="after")
    def _check_intent_consistency(self) -> "ProstheticCommand":
        if self.intent == "gesture":
            if self.gesture is None:
                raise ValueError("intent='gesture' requires a non-null 'gesture' letter.")
            if self.commands:
                raise ValueError("intent='gesture' must not carry individual 'commands'.")
        elif self.intent == "joint_positions":
            if not self.commands:
                raise ValueError("intent='joint_positions' requires at least one command.")
            if self.gesture is not None:
                raise ValueError("intent='joint_positions' must set 'gesture' to null.")
        elif self.intent == "stop":
            if self.gesture != ControlCommand.STOP.value:
                raise ValueError("intent='stop' requires gesture='S'.")
            if self.commands:
                raise ValueError("intent='stop' must not carry individual 'commands'.")
        elif self.intent == "no_action":
            if self.commands or self.gesture is not None:
                raise ValueError("intent='no_action' must carry no gesture and no commands.")
            if self.serial_command.strip().upper() != "NONE":
                raise ValueError("intent='no_action' requires serial_command='NONE'.")

        seen: set[str] = set()
        for command in self.commands:
            if command.actuator in seen:
                raise ValueError(f"Actuator {command.actuator!r} commanded more than once.")
            seen.add(command.actuator)

        for channel in self.dominant_channels:
            if channel not in EMG_CHANNELS:
                raise ValueError(
                    f"Unknown EMG channel {channel!r}. Valid: {list(EMG_CHANNELS)}"
                )
        return self

    @property
    def handedness(self) -> Handedness:
        return Handedness(self.hand)


def llm_json_schema() -> dict:
    """JSON Schema injected into the technical context and used for structured
    output / tool-calling when the provider supports it."""
    return ProstheticCommand.model_json_schema()
