"""Sending a command by hand, and logging every command that was sent.

Two things live here because they are the same question from two sides: *can I
put a command on the wire and see the hand move?*, and *what has actually been
put on the wire?*

The manual path exists to separate two failures that look identical from the
outside. When a run produces no movement, it is either the model's answer or the
plumbing — the validator, the WebSocket, the serial link, the firmware. Typing
`C` and watching the hand close settles it in one action, with no inference
involved.

It is deliberately *not* a shortcut around validation. A manually typed command
goes through the same seven stages as a model's, for the same reason: the
mechanical stops do not care who chose the number, and a typo in a text field
can strip a gearmotor exactly as well as a bad model can.
"""

from __future__ import annotations

import json

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import current_context
from app.domain.hand_spec import Handedness, LimitProfile, get_limit_profile
from app.models.movement_log import MovementLogEntry, MovementSource
from app.validation.pipeline import validate_response
from app.validation.results import ValidationReport


class ManualCommandError(ValueError):
    """The typed command cannot be sent, with the reason a human can act on."""

    def __init__(self, message: str, report: ValidationReport | None = None):
        super().__init__(message)
        self.report = report


def validate_manual_command(
    command: str,
    *,
    handedness: Handedness = Handedness.RIGHT,
    profile: LimitProfile | None = None,
) -> ValidationReport:
    """Put a typed command through the model's own validation pipeline.

    The command is wrapped in the response shape the pipeline expects rather
    than validated by a second, parallel code path. A separate validator for
    manual commands would be a second definition of "safe", and the two would
    drift — at which point the safety guarantee is whichever one happens to run.

    Raises
    ------
    ManualCommandError
        With the first blocking issue's message, which already names the
        actuator, the value and the profile that rejected it.
    """
    text = (command or "").strip().upper()
    if not text:
        raise ManualCommandError("Type a command first, for example C or A320,B180.")

    tokens = [token.strip() for token in text.split(",") if token.strip()]
    positions = [token for token in tokens if len(token) > 1]
    is_gesture = bool(tokens) and not positions

    payload = {
        "intent": "stop" if text == "S" else "gesture" if is_gesture else "joint_positions",
        "gesture": tokens[0] if is_gesture else None,
        "commands": [
            {"actuator": token[0], "position": int(token[1:])}
            for token in positions
            if token[1:].lstrip("-").isdigit()
        ],
        "serial_command": ",".join(tokens),
        "confidence": 1.0,
        "safety": {"within_limits": True},
    }

    report = validate_response(
        json.dumps(payload),
        expected_hand=handedness,
        limit_profile=profile or get_limit_profile(),
    )
    if not report.passed:
        first = report.errors[0] if report.errors else None
        raise ManualCommandError(
            first.message if first else "The command failed validation.", report
        )
    return report


async def record(
    session: AsyncSession,
    *,
    serial_command: str,
    handedness: str,
    source: MovementSource,
    actuator_positions: dict | None = None,
    duration_ms: int | None = None,
    execution_id=None,
    sent_to_simulator: bool = False,
    sent_to_prosthesis: bool = False,
    transport: str | None = None,
    delivery_error: str | None = None,
    notes: str | None = None,
) -> MovementLogEntry:
    """Append one transmission to the log.

    Called after the attempt, not before, so the two destination flags record
    what happened rather than what was intended. A log written up front would
    claim delivery for a command the link dropped.
    """
    entry = MovementLogEntry(
        serial_command=serial_command,
        handedness=handedness,
        actuator_positions=actuator_positions or {},
        duration_ms=duration_ms,
        source=source.value,
        execution_id=execution_id,
        triggered_by_email=current_context().actor_email,
        sent_to_simulator=sent_to_simulator,
        sent_to_prosthesis=sent_to_prosthesis,
        transport=transport,
        delivery_error=delivery_error,
        notes=notes,
    )
    session.add(entry)
    await session.flush()
    return entry


async def recent(
    session: AsyncSession,
    *,
    limit: int = 200,
    source: str | None = None,
) -> list[MovementLogEntry]:
    """The log, newest first."""
    stmt = (
        select(MovementLogEntry)
        .order_by(desc(MovementLogEntry.created_at))
        .limit(limit)
    )
    if source:
        stmt = stmt.where(MovementLogEntry.source == source)
    return list((await session.execute(stmt)).scalars().all())
