from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Permission, require_permission
from app.db.session import get_session
from app.domain.hand_spec import Handedness
from app.models.experiment import Execution
from app.models.feedback import GestureFeedback
from app.models.user import User
from app.prompts.dynamic_prompt import DynamicContent
from app.schemas.emg import EmgSourceMode, EmgWindow
from app.schemas.feedback import FeedbackResult, GestureFeedbackIn, GestureFeedbackOut
from app.schemas.multimodal import MechanicalTelemetry
from app.services.execution_service import run_execution

router = APIRouter(prefix="/feedback", tags=["gesture-feedback"])


@router.get("/execution/{execution_id}", response_model=list[GestureFeedbackOut])
async def list_feedback(execution_id: uuid.UUID,
                        _: User = Depends(require_permission(Permission.VIEW_RESULTS)),
                        session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(select(GestureFeedback).where(
        GestureFeedback.execution_id == execution_id).order_by(GestureFeedback.created_at))
    return list(rows)


@router.post("/execution/{execution_id}", response_model=FeedbackResult)
async def submit_feedback(execution_id: uuid.UUID, payload: GestureFeedbackIn,
                          user: User = Depends(require_permission(Permission.LABEL_GESTURES)),
                          session: AsyncSession = Depends(get_session)):
    execution = await session.get(Execution, execution_id)
    if execution is None or execution.emg_window is None:
        raise HTTPException(404, "Execution or its EMG window was not found.")
    try:
        current_attempt = max(
            1, int((execution.custom_parameters or {}).get("feedback_attempt", 1))
        )
    except (TypeError, ValueError):
        current_attempt = 1
    feedback = GestureFeedback(
        execution_id=execution.id, evaluator_id=user.id, evaluator_email=user.email,
        source=payload.source, is_correct=payload.is_correct, score=payload.score,
        expected_gesture=payload.expected_gesture, observed_gesture=payload.observed_gesture,
        notes=payload.notes, sensor_snapshot=payload.sensor_snapshot,
        correction_attempt=current_attempt - 1,
    )
    session.add(feedback)
    await session.flush()
    correction = None
    if payload.auto_retry and not payload.is_correct:
        if current_attempt >= payload.max_attempts:
            raise HTTPException(409, "Maximum corrective attempts reached.")
        if execution.sampling_configuration_id is None:
            raise HTTPException(409, "The original sampling configuration is unavailable.")
        evidence = {
            "previous_command": (execution.parsed_response or {}).get("serial_command"),
            "expected_gesture": payload.expected_gesture,
            "observed_gesture": payload.observed_gesture,
            "reviewer_notes": payload.notes,
            "sensor_evidence": payload.sensor_snapshot,
            "instruction": "Correct the command using this feedback. Return only the required JSON object.",
        }
        prior_dynamic = execution.dynamic_prompt_text or ""
        corrective_dynamic = prior_dynamic + "\n\nGESTURE EXECUTION FEEDBACK:\n" + json.dumps(evidence)
        record = execution.emg_window
        window = EmgWindow(
            samples=record.samples, source_mode=EmgSourceMode(record.source_mode),
            sample_rate_hz=record.sample_rate_hz, captured_at=record.captured_at,
            ground_truth_gesture=record.ground_truth_gesture, notes=record.notes,
        )
        telemetry_payload = payload.sensor_snapshot.get("mechanical_telemetry")
        mechanical_telemetry = (
            MechanicalTelemetry.model_validate(telemetry_payload)
            if telemetry_payload else None
        )
        correction = await run_execution(
            session, sampling_configuration_id=execution.sampling_configuration_id,
            invocation_mode=(execution.custom_parameters or {}).get(
                "invocation_mode", "structured_output"
            ),
            window=window, handedness=Handedness(execution.handedness),
            system_prompt_override=execution.system_prompt_text,
            technical_context_override=execution.technical_context_text,
            emg_context_override=execution.emg_context_text,
            dynamic_template_override=corrective_dynamic,
            dynamic_content=DynamicContent(execution.dynamic_content),
            expected_serial_command=execution.expected_serial_command,
            limit_profile_id=execution.limit_profile, experiment_id=execution.experiment_id,
            project_id=execution.project_id, triggered_by_id=user.id,
            experiment_type="feedback_correction",
            subject_ref=record.subject_ref,
            mechanical_telemetry=mechanical_telemetry,
            extra_parameters={"feedback_parent_execution": str(execution.id),
                              "feedback_attempt": current_attempt + 1},
        )
        correction.retry_of_id = execution.id
        feedback.correction_execution_id = correction.id
    await session.commit()
    await session.refresh(feedback)
    return FeedbackResult(feedback=GestureFeedbackOut.model_validate(feedback),
                          correction_execution_id=correction.id if correction else None)
