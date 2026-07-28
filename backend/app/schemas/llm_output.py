"""The contract between an arbitrary language model and a physical actuator.

The model emits **one line: the serial command**. Nothing else.

    C
    A320,B180,E45
    S

That is the whole contract. It used to be a ten-field JSON object, most of which
was the model's own account of what it had decided — confidence, a pattern
label, a safety self-assessment. None of that was a measurement: the backend
already re-derives every safety property independently and never trusted the
model's version. What remains is the only thing that reaches the prosthesis.

The reduction is not only tidier. A response of two characters instead of two
hundred tokens removes most of the surface a small model has to get wrong, and
the failure modes that dominated — prose around the JSON, invented fields, a
`serial_command` disagreeing with the structured fields it sat beside — cannot
occur at all.

Everything downstream still works with a structured object: metrics, the
simulator frame, the export. That object is now *derived* from the command
rather than parsed from the response, which is why it can no longer contradict
it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.hand_spec import (
    ACTUATORS,
    GESTURES,
    Actuator,
    ControlCommand,
    Handedness,
)
from app.domain.protocol import SerialFrame

#: What the model is asked to send when the window shows no actionable intent.
#: A command is required in every response, so "do nothing" needs a spelling;
#: `O` (open) is the documented rest pose and is always safe to execute.
NO_ACTION_COMMAND: str = "O"


@dataclass(slots=True)
class ProstheticCommand:
    """The internal representation, derived from the emitted command line.

    Kept as a structure because every consumer downstream — metrics, the
    simulator, the export, the audit record — was built around one. The
    difference is that nothing here is asserted by the model: each field is
    computed from the command, so the record cannot disagree with what was
    actually sent.
    """

    hand: str
    serial_command: str
    intent: str
    gesture: str | None = None
    commands: list[dict[str, Any]] = field(default_factory=list)
    detected_pattern: str | None = None

    @property
    def handedness(self) -> Handedness:
        return Handedness(self.hand)

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        """Serialised form stored on the execution and returned by the API."""
        return {
            "hand": self.hand,
            "serial_command": self.serial_command,
            "intent": self.intent,
            "gesture": self.gesture,
            "commands": self.commands,
            "detected_pattern": self.detected_pattern,
        }


def describe_command(frame: SerialFrame, handedness: Handedness) -> ProstheticCommand:
    """Build the internal representation from a parsed serial frame.

    The `detected_pattern` label is derived from the gesture the firmware would
    execute, not claimed by the model. It is therefore a description of the
    command rather than an opinion about the EMG — which is what it always
    should have been, since it is used to group results.
    """
    controls = frame.controls
    positions = frame.positions

    if controls:
        command = controls[0]
        gesture = GESTURES[command]
        intent = "stop" if command is ControlCommand.STOP else "gesture"
        return ProstheticCommand(
            hand=handedness.value,
            serial_command=frame.encode(),
            intent=intent,
            gesture=command.value,
            detected_pattern=gesture.name.lower(),
        )

    return ProstheticCommand(
        hand=handedness.value,
        serial_command=frame.encode(),
        intent="joint_positions",
        commands=[
            {"actuator": actuator.value, "position": position,
             "label": ACTUATORS[actuator].label}
            for actuator, position in positions.items()
        ],
        detected_pattern="custom_pose",
    )


def output_contract() -> str:
    """The contract as stated to the model, in the technical context."""
    letters = " ".join(a.value for a in Actuator)
    gestures = " ".join(c.value for c in GESTURES)
    return (
        "Reply with ONE LINE containing ONLY the serial command. No JSON, no "
        "prose, no explanation, no code fence, no trailing text.\n\n"
        f"  position form : <LETTER><INTEGER>, comma separated   ({letters})\n"
        f"  gesture form  : a single letter                      ({gestures})\n\n"
        "Examples of a complete, correct reply:\n"
        "  C\n"
        "  A320,B180,C400,D200\n"
        "  E120,F350\n"
        "  S\n\n"
        f"If the window shows no actionable intent, reply `{NO_ACTION_COMMAND}` "
        "to hold the hand open."
    )
