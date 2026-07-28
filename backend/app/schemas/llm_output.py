"""The contract between an arbitrary language model and a physical actuator.

The model emits a JSON object. ``serial_command`` is the only field that ever
reaches the prosthesis; everything beside it is the model's own account of the
decision — which pattern it believed it saw, how confident it was, whether it
considered the pose safe.

None of those self-reports is trusted. The backend re-derives every safety
property from the command itself, independently, in
:mod:`app.validation.pipeline`. They are recorded because *whether a model's
self-report matches reality* is one of the questions this platform exists to
answer: a model returning 0.95 confidence on a command that fails range
validation is a different and more dangerous failure than one returning 0.3.

The structured fields are also what makes disagreement detectable at all. With
a bare command line there is only one representation, so nothing can contradict
anything; with both, the `consistency` stage can catch a `serial_command` that
says one thing while `intent`, `gesture` and `commands` say another. That
disagreement is a real observed failure mode in small models, and silently
accepting whichever field happened to be right would hide it.

Fields are validated but never *corrected*. A response that misstates its own
command is a failed response, not a response to be repaired.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.hand_spec import (
    GESTURES,
    SAFETY,
    Actuator,
    ControlCommand,
    Handedness,
)

#: The intent a model declares when the window carries no actionable movement.
NO_ACTION_INTENT: str = "no_action"

#: The command that expresses "do nothing" on the wire. `O` (open) is the
#: documented rest pose and is always safe to execute, so a `no_action` verdict
#: still leaves the hand somewhere defined rather than wherever it happened to
#: be.
NO_ACTION_COMMAND: str = "O"

#: The labels the system prompt enumerates for `detected_pattern`. Recorded and
#: compared against this set, but a value outside it is not a parse failure: a
#: model inventing a label is a finding worth keeping, and the command it sent
#: is checked on its own terms regardless.
DETECTED_PATTERNS: tuple[str, ...] = (
    "rest",
    "power_grasp",
    "precision_pinch",
    "lateral_pinch",
    "hand_open",
    "wrist_flexion",
    "co_contraction",
)

_GESTURE_LETTERS = tuple(command.value for command in GESTURES)
_ACTUATOR_LETTERS = tuple(actuator.value for actuator in Actuator)


class CommandEntry(BaseModel):
    """One actuator driven to one absolute position.

    ``position`` is deliberately unbounded here. The documented range depends on
    which limit profile the execution runs under, and the manual contradicts
    itself about what that range is — so the bound lives in the profile and is
    enforced by the `range` stage, which records *which* profile rejected the
    value. Enforcing a guess at this layer would turn a measurable,
    attributable failure into an opaque schema error.
    """

    model_config = ConfigDict(extra="forbid")

    actuator: Literal[_ACTUATOR_LETTERS]  # type: ignore[valid-type]
    position: int
    speed_pct: Annotated[int, Field(
        ge=SAFETY.min_speed_pct,
        le=SAFETY.max_speed_pct,
    )] = SAFETY.default_speed_pct


class SafetyAssertion(BaseModel):
    """The model's own claim about its command. Advisory, never authoritative.

    The system prompt tells the model this block is advisory and that
    dishonesty is a failure. That framing only means anything if the claim is
    checked: `within_limits: true` on a command the `range` stage rejects is
    recorded as a false safety assertion, and it is among the more useful
    things this platform measures — a model that is wrong is recoverable, a
    model that is wrong *and* reports itself safe is not.
    """

    model_config = ConfigDict(extra="forbid")

    within_limits: bool


class ProstheticCommand(BaseModel):
    """A complete response, exactly as the model stated it.

    Nothing here is normalised on the way in. What is stored is what the model
    said, so an execution can be replayed and re-judged later without the
    original response having been quietly improved first.
    """

    model_config = ConfigDict(extra="forbid")

    hand: Literal["right", "left"]
    intent: Literal["gesture", "joint_positions", "stop", "no_action"]
    gesture: Literal[_GESTURE_LETTERS] | None = None  # type: ignore[valid-type]
    commands: list[CommandEntry] = Field(default_factory=list)
    serial_command: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    safety: SafetyAssertion | None = None

    #: Enumerated in the system prompt but absent from the response shape stated
    #: in the technical context, so models will differ on whether they send it.
    #: Optional rather than required: rejecting a response for omitting a
    #: descriptive label, while the command it carries is perfectly valid, would
    #: throw away a usable result over a documentation inconsistency.
    detected_pattern: str | None = None

    @property
    def handedness(self) -> Handedness:
        return Handedness(self.hand)


def derive_pattern(gesture: ControlCommand | None) -> str:
    """The pattern label implied by the command, for grouping results.

    Used when the model omits `detected_pattern`, so every execution can be
    grouped by what it actually did rather than only those that volunteered a
    label.
    """
    if gesture is None:
        return "custom_pose"
    return GESTURES[gesture].name.lower()


def output_contract() -> str:
    """The response shape as stated to the model, in the technical context."""
    gestures = "|".join(f'"{letter}"' for letter in _GESTURE_LETTERS)
    first, last = _ACTUATOR_LETTERS[0], _ACTUATOR_LETTERS[-1]
    return (
        "OUTPUT\n"
        "Valid JSON only. No prose.\n"
        "{\n"
        '  "hand":"right"|"left",\n'
        '  "intent":"gesture"|"joint_positions"|"stop"|"no_action",\n'
        f'  "gesture":{gestures}|null,\n'
        f'  "commands":[{{"actuator":"{first}".."{last}","position":int,'
        f'"speed_pct":{SAFETY.min_speed_pct}-{SAFETY.max_speed_pct}}}],\n'
        '  "serial_command":string,\n'
        '  "confidence":float,\n'
        '  "safety":{"within_limits":bool}\n'
        "}"
    )


def response_json_schema() -> dict[str, Any]:
    """The schema sent as `response_format` so the runtime constrains decoding.

    Structured output removes the largest single failure mode — prose wrapped
    around the JSON — before it can happen, rather than catching it afterwards
    in the parse stage.
    """
    return ProstheticCommand.model_json_schema()
