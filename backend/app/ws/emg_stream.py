"""WebSocket layer: live EMG ingestion and simulator movement fan-out.

Two channels:

``/ws/emg/{session_key}``
    The acquisition device (or a bridge process) pushes 8-channel windows.
    With ``auto_run`` set, each frame immediately triggers a full execution
    using the configuration pinned to that session - this is the "live" half of
    the manual/live toggle in the left panel.

``/ws/simulator``
    The Angular simulator subscribes here and receives validated poses only.
    A pose that failed validation is never broadcast, so the renderer is
    structurally incapable of showing an unsafe movement.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.domain.hand_spec import Handedness
from app.models.emg import EmgStreamSession
from app.schemas.emg import EmgStreamFrame
from app.services.execution_service import ExecutionRequestError, run_execution

logger = get_logger(__name__)
router = APIRouter()


class ConnectionRegistry:
    """In-process fan-out. Deliberately not a message broker: a single research
    workstation drives one simulator, and an extra hop would add latency to a
    loop we are trying to measure."""

    def __init__(self) -> None:
        self._simulators: set[WebSocket] = set()
        self._emg_sessions: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def attach_simulator(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._simulators.add(websocket)

    async def detach_simulator(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._simulators.discard(websocket)

    async def publish(self, payload: dict[str, Any]) -> int:
        async with self._lock:
            targets = list(self._simulators)
        delivered = 0
        for websocket in targets:
            try:
                await websocket.send_json(payload)
                delivered += 1
            except Exception:
                await self.detach_simulator(websocket)
        return delivered

    def pin_session(self, session_key: str, config: dict[str, Any]) -> None:
        self._emg_sessions[session_key] = config

    def session_config(self, session_key: str) -> dict[str, Any]:
        return self._emg_sessions.get(session_key, {})


registry = ConnectionRegistry()


async def broadcast_movement(execution) -> int:
    """Send a validated pose to every attached simulator."""
    movement = execution.movement
    if movement is None:
        return 0
    payload = {
        "type": "movement",
        "execution_id": str(execution.id),
        "status": execution.status,
        "handedness": movement.handedness,
        "limit_profile": movement.limit_profile,
        "source": movement.source,
        "serial_command": movement.serial_command,
        "actuator_positions": movement.actuator_positions,
        "actuator_normalised": movement.actuator_normalised,
        "joint_angles": movement.joint_angles,
        "duration_ms": movement.duration_ms,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
    }
    delivered = await registry.publish(payload)
    if delivered:
        movement.was_rendered = True
    return delivered


async def publish_pose(
    serial_command: str,
    *,
    pose,
    handedness,
    source: str,
) -> int:
    """Push a pose that has no Execution behind it.

    `broadcast_movement` needs a stored `SimulatorMovement`, which only exists
    for a model run. A manual test has no execution and no metrics — it is a
    command and a resolved pose — but the simulator must render it identically,
    or the test would prove nothing about the path a real command takes.

    The payload keeps the same shape for exactly that reason: the simulator has
    one code path, and it cannot tell a hand-typed command from a model's.
    """
    # `HandPose.to_dict()` rather than a hand-rolled walk over the fields.
    #
    # The first version read `state.__dict__` for each joint, which raised
    # AttributeError: `JointState` is a slots dataclass and has no instance
    # dictionary. But the deeper mistake was writing a second serialiser at all:
    # `to_dict` already exists, already rounds the angles the way the stored
    # movements are rounded, and is the shape the simulator was built to parse.
    # A parallel one could only ever agree or drift.
    resolved = pose.to_dict() if pose else {}

    payload = {
        "type": "movement",
        "execution_id": None,
        "status": "manual",
        "handedness": resolved.get(
            "handedness",
            handedness.value if hasattr(handedness, "value") else handedness,
        ),
        "limit_profile": resolved.get("limit_profile"),
        "source": source,
        "serial_command": serial_command,
        "actuator_positions": resolved.get("actuator_positions", {}),
        "actuator_normalised": resolved.get("actuator_normalised", {}),
        # The stored-movement path names this field `joint_angles`, and the
        # simulator reads that name. `to_dict` calls it `joints`.
        "joint_angles": resolved.get("joints", []),
        "duration_ms": resolved.get("duration_ms", 0),
        "emitted_at": datetime.now(timezone.utc).isoformat(),
    }
    return await registry.publish(payload)


async def broadcast_rejection(execution, reason: str, stage: str | None) -> int:
    """Tell the simulator that a response was rejected, so it can show the
    failure without moving the hand."""
    return await registry.publish(
        {
            "type": "rejected",
            "execution_id": str(execution.id),
            "status": execution.status,
            "failed_stage": stage,
            "reason": reason,
            "emitted_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.websocket("/ws/simulator")
async def simulator_socket(websocket: WebSocket) -> None:
    """Read-only feed of validated movements."""
    await websocket.accept()
    await registry.attach_simulator(websocket)
    await websocket.send_json({"type": "connected", "channel": "simulator"})
    try:
        while True:
            # The simulator has no manual controls; inbound traffic is heartbeat only.
            await websocket.receive_text()
            await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await registry.detach_simulator(websocket)


@router.websocket("/ws/emg/{session_key}")
async def emg_socket(websocket: WebSocket, session_key: str) -> None:
    """Live 8-channel EMG ingestion.

    Protocol
    --------
    First message (optional) configures the session::

        {"type": "configure",
         "sampling_configuration_id": "...", "handedness": "right",
         "auto_run": true, "subject_ref": "S01"}

    Subsequent messages are ``EmgStreamFrame`` payloads.
    """
    await websocket.accept()
    await websocket.send_json({"type": "connected", "channel": "emg", "session": session_key})

    async with AsyncSessionLocal() as db:
        stream = EmgStreamSession(
            session_key=session_key, started_at=datetime.now(timezone.utc)
        )
        db.add(stream)
        await db.commit()

    frames = 0
    triggered = 0

    try:
        while True:
            message = await websocket.receive_json()
            kind = message.get("type", "frame")

            if kind == "configure":
                registry.pin_session(
                    session_key,
                    {
                        "sampling_configuration_id": message.get("sampling_configuration_id"),
                        "handedness": message.get("handedness", "right"),
                        "auto_run": bool(message.get("auto_run", False)),
                        "subject_ref": message.get("subject_ref"),
                        "limit_profile": message.get("limit_profile"),
                        "experiment_id": message.get("experiment_id"),
                    },
                )
                await websocket.send_json({"type": "configured", "session": session_key})
                continue

            if kind == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            try:
                frame = EmgStreamFrame.model_validate(
                    {**message, "session_id": message.get("session_id", session_key)}
                )
            except ValidationError as exc:
                await websocket.send_json(
                    {"type": "error", "detail": "Invalid EMG frame.", "errors": exc.errors()}
                )
                continue

            frames += 1
            config = registry.session_config(session_key)
            should_run = frame.auto_run or config.get("auto_run", False)
            config_id = config.get("sampling_configuration_id")

            await websocket.send_json(
                {
                    "type": "frame_ack",
                    "sequence": frame.sequence,
                    "mean_rms": round(frame.window.total_activation, 4),
                    "will_execute": bool(should_run and config_id),
                }
            )

            if not (should_run and config_id):
                continue

            async with AsyncSessionLocal() as db:
                try:
                    execution = await run_execution(
                        db,
                        sampling_configuration_id=uuid.UUID(str(config_id)),
                        window=frame.window,
                        handedness=Handedness(config.get("handedness", "right")),
                        limit_profile_id=config.get("limit_profile"),
                        experiment_id=(
                            uuid.UUID(str(config["experiment_id"]))
                            if config.get("experiment_id") else None
                        ),
                        experiment_type="live_stream",
                        subject_ref=config.get("subject_ref"),
                        emg_session_id=session_key,
                        emg_sequence=frame.sequence,
                    )
                    await db.commit()
                except ExecutionRequestError as exc:
                    await db.rollback()
                    await websocket.send_json({"type": "error", "detail": str(exc)})
                    continue

                triggered += 1
                if execution.validation_passed and execution.movement is not None:
                    await broadcast_movement(execution)
                    await db.commit()
                else:
                    result = execution.validation_result
                    await broadcast_rejection(
                        execution,
                        reason=(
                            result.issues[0].message
                            if result and result.issues else "Validation failed."
                        ),
                        stage=result.failed_stage if result else None,
                    )

                await websocket.send_json(
                    {
                        "type": "execution_result",
                        "execution_id": str(execution.id),
                        "status": execution.status,
                        "validation_passed": execution.validation_passed,
                        "latency_ms": execution.latency_ms,
                        "sequence": frame.sequence,
                    }
                )

    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("emg_socket_error", extra={"session": session_key, "error": str(exc)})
    finally:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            row = (
                await db.execute(
                    select(EmgStreamSession).where(
                        EmgStreamSession.session_key == session_key
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                row.frames_received = frames
                row.executions_triggered = triggered
                row.ended_at = datetime.now(timezone.utc)
                await db.commit()
