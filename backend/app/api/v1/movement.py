"""Send a command by hand, and read the log of everything that was sent.

Two endpoints, and the manual one exists to separate two failures that look
identical from the outside. When a run produces no movement, the cause is either
the model's answer or the plumbing — validator, WebSocket, serial link,
firmware. Typing `C` and watching the hand close settles that in one action,
with no inference in the way.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Permission, require_permission
from app.db.session import get_session
from app.domain.hand_spec import get_limit_profile
from app.models.movement_log import MovementSource
from app.models.user import User
from app.schemas.api import ManualCommandIn, ManualCommandOut, MovementLogOut
from app.services import movement_service
from app.ws.emg_stream import publish_pose

router = APIRouter(prefix="/movement", tags=["movement"])


@router.post("/send", response_model=ManualCommandOut)
async def send_manual_command(
    payload: ManualCommandIn,
    _: User = Depends(require_permission(Permission.OPERATE_HARDWARE)),
    session: AsyncSession = Depends(get_session)
) -> ManualCommandOut:
    """Validate a typed command and push it to the simulator.

    Validated through the *same* seven stages a model's answer goes through, not
    a parallel checker. Two definitions of "safe" would drift, and the guarantee
    would become whichever one happened to run. The mechanical stops do not care
    who chose the number: a typo in a text field can strip a gearmotor exactly
    as well as a bad model can.

    Delivery to the prosthesis happens in the browser, which is where the serial
    link lives — the backend cannot reach it. The response says what was
    published; the browser reports back what the hardware did, and the log
    records both.
    """
    profile = get_limit_profile(payload.limit_profile.value if payload.limit_profile else None)

    try:
        report = movement_service.validate_manual_command(
            payload.serial_command,
            handedness=payload.handedness,
            profile=profile,
        )
    except movement_service.ManualCommandError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    pose = report.resolved_pose
    delivered = await publish_pose(
        report.normalised_serial or "",
        pose=pose,
        handedness=payload.handedness,
        source=MovementSource.MANUAL.value,
    )

    entry = await movement_service.record(
        session,
        serial_command=report.normalised_serial or payload.serial_command,
        handedness=payload.handedness.value,
        source=MovementSource.MANUAL,
        actuator_positions=pose.actuator_positions if pose else {},
        duration_ms=pose.duration_ms if pose else None,
        sent_to_simulator=delivered > 0,
        # The browser owns the serial link, so it confirms hardware delivery in a
        # follow-up call. Claiming it here would be a guess recorded as fact.
        sent_to_prosthesis=False,
        notes=payload.notes,
    )

    return ManualCommandOut(
        id=entry.id,
        serial_command=entry.serial_command,
        normalised_serial=report.normalised_serial,
        actuator_positions=entry.actuator_positions,
        duration_ms=entry.duration_ms,
        simulator_clients=delivered,
        warnings=[issue.message for issue in report.warnings],
    )


@router.post("/log/{entry_id}/delivered", response_model=MovementLogOut)
async def confirm_hardware_delivery(
    entry_id: str,
    transport: str = Query(..., pattern="^(serial|ble)$"),
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> MovementLogOut:
    """The browser reporting what the prosthesis actually did with a command.

    A separate call because the two destinations succeed and fail
    independently: the simulator renders from the backend, the hardware is
    driven from the browser, and either can work while the other does not. One
    combined write would have to guess at the half it cannot see.
    """
    entries = await movement_service.recent(session, limit=500)
    entry = next((e for e in entries if str(e.id) == entry_id), None)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Log entry not found.")

    entry.sent_to_prosthesis = error is None
    entry.transport = transport if error is None else None
    entry.delivery_error = error
    return MovementLogOut.model_validate(entry)


@router.get("/log", response_model=list[MovementLogOut])
async def read_movement_log(
    limit: int = Query(default=200, le=1000),
    source: str | None = Query(default=None, pattern="^(execution|manual|replay)$"),
    session: AsyncSession = Depends(get_session),
) -> list[MovementLogOut]:
    """Every command that reached the simulator or the prosthesis, newest first.

    Distinct from the execution history: that records what models answered, this
    records what moved the hand — including commands typed by hand and replays,
    which move it exactly as a model's answer does.
    """
    entries = await movement_service.recent(session, limit=limit, source=source)
    return [MovementLogOut.model_validate(entry) for entry in entries]
