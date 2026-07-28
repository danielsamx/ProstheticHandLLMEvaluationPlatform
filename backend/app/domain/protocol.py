"""Serial protocol codec for the HANDi EPN V3 Bluetooth link.

Wire format (Manual V3, 'Uso de la Mano Robotica')::

    A320,B120,E45\n      -> individual actuator positions, comma separated
    P\n                  -> single-letter preset gesture
    S\n                  -> emergency stop

The parser resolves the ``C`` ambiguity documented in :class:`ControlCommand`:
a bare ``C`` closes the hand, ``C<int>`` addresses the middle finger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.hand_spec import (
    ACTUATORS,
    EXCLUSIVE_COMMANDS,
    GESTURES,
    PROTOCOL,
    Actuator,
    ControlCommand,
)

_TOKEN_RE = re.compile(r"^([A-Z])(-?\d+)?$")

#: Letters that are valid position commands.
_POSITION_LETTERS = {a.value for a in Actuator}
#: Letters that are valid bare control commands.
_CONTROL_LETTERS = {c.value for c in ControlCommand}


class ProtocolError(ValueError):
    """Raised when a serial frame cannot be represented on the wire."""


@dataclass(frozen=True, slots=True)
class PositionToken:
    actuator: Actuator
    position: int

    def encode(self) -> str:
        return f"{self.actuator.value}{self.position}"


@dataclass(frozen=True, slots=True)
class ControlToken:
    command: ControlCommand

    def encode(self) -> str:
        return self.command.value


Token = PositionToken | ControlToken


@dataclass(frozen=True, slots=True)
class SerialFrame:
    """A fully parsed transmission line."""

    tokens: tuple[Token, ...]
    raw: str

    @property
    def positions(self) -> dict[Actuator, int]:
        return {t.actuator: t.position for t in self.tokens if isinstance(t, PositionToken)}

    @property
    def controls(self) -> tuple[ControlCommand, ...]:
        return tuple(t.command for t in self.tokens if isinstance(t, ControlToken))

    @property
    def is_emergency_stop(self) -> bool:
        return ControlCommand.STOP in self.controls

    def encode(self) -> str:
        return PROTOCOL.separator.join(t.encode() for t in self.tokens)


def parse_serial_command(line: str) -> SerialFrame:
    """Parse one ASCII transmission line into a :class:`SerialFrame`.

    Raises
    ------
    ProtocolError
        If any token is malformed or references an unknown command letter.
    """
    raw = (line or "").strip().strip(PROTOCOL.separator)
    if not raw:
        raise ProtocolError("Empty serial frame.")
    if len(raw) > PROTOCOL.max_line_length:
        raise ProtocolError(
            f"Serial frame exceeds {PROTOCOL.max_line_length} characters "
            f"({len(raw)} given)."
        )

    tokens: list[Token] = []
    for chunk in (c.strip() for c in raw.split(PROTOCOL.separator)):
        if not chunk:
            continue
        match = _TOKEN_RE.match(chunk)
        if not match:
            raise ProtocolError(f"Malformed token {chunk!r}.")
        letter, value = match.group(1), match.group(2)

        if value is None:
            # Bare letter -> control command (this is how 'C' means CLOSE).
            if letter not in _CONTROL_LETTERS:
                raise ProtocolError(
                    f"Unknown control command {letter!r}. "
                    f"Valid: {sorted(_CONTROL_LETTERS)}"
                )
            tokens.append(ControlToken(ControlCommand(letter)))
        else:
            if letter not in _POSITION_LETTERS:
                raise ProtocolError(
                    f"Command {letter!r} does not accept a position argument. "
                    f"Position commands: {sorted(_POSITION_LETTERS)}"
                )
            tokens.append(PositionToken(Actuator(letter), int(value)))

    if not tokens:
        raise ProtocolError("Serial frame contained no tokens.")

    controls = [t.command for t in tokens if isinstance(t, ControlToken)]
    exclusive = [c for c in controls if c in EXCLUSIVE_COMMANDS]
    if exclusive and len(tokens) > 1:
        raise ProtocolError(
            f"Command {exclusive[0].value!r} is exclusive and must be sent alone."
        )
    if len(controls) > 1:
        raise ProtocolError("At most one preset gesture may be sent per frame.")
    if controls and len(tokens) > 1:
        raise ProtocolError(
            "A preset gesture cannot be combined with individual actuator positions."
        )

    seen: set[Actuator] = set()
    for token in tokens:
        if isinstance(token, PositionToken):
            if token.actuator in seen:
                raise ProtocolError(
                    f"Actuator {token.actuator.value!r} addressed more than once."
                )
            seen.add(token.actuator)

    return SerialFrame(tuple(tokens), raw)


def encode_positions(positions: dict[Actuator, int]) -> str:
    """Serialise actuator positions in canonical A-F order."""
    if not positions:
        raise ProtocolError("No positions to encode.")
    ordered = [a for a in Actuator if a in positions]
    return PROTOCOL.separator.join(f"{a.value}{int(positions[a])}" for a in ordered)


def encode_gesture(command: ControlCommand) -> str:
    """Serialise a preset gesture."""
    if command not in GESTURES:
        raise ProtocolError(f"Unknown gesture {command!r}.")
    return command.value


def describe_command_set() -> str:
    """Human/LLM-readable command table, used by the technical context builder."""
    lines = ["POSITION COMMANDS (letter + integer encoder position):"]
    for actuator, spec in ACTUATORS.items():
        lines.append(
            f"  {actuator.value}<position>  -> {spec.label:<12} ({spec.digit.value}) - {spec.description}"
        )
    lines.append("")
    lines.append("PRESET GESTURE COMMANDS (single letter, no argument):")
    for command, gesture in GESTURES.items():
        lines.append(f"  {command.value}  -> {gesture.name:<13} - {gesture.description}")
    return "\n".join(lines)


def normalise_expected_command(command: str | None) -> str | None:
    """Tidy a hand-typed expected command without interpreting it.

    Upper-cased and stripped of spaces around separators, because `a320, b180`
    and `A320,B180` drive the hand identically and a researcher should not have
    to match the wire format exactly to get a correct comparison.

    Deliberately not parsed or validated. An expected command that turns out to
    be malformed is the researcher's own mistake to see in the dashboard, and
    rejecting it at entry would stop them recording a run while they work out
    what the right answer is.

    Lives here rather than in the execution service because it is a statement
    about command syntax, and because the service cannot be imported without
    litellm — which would make this untestable in any environment lacking a
    heavyweight optional dependency it does not use.
    """
    if command is None:
        return None
    cleaned = ",".join(part.strip() for part in command.strip().upper().split(","))
    return cleaned or None
