"""Hardware specification endpoint.

The Angular simulator builds its rig, limits and gesture list from this payload,
so there is exactly one definition of the prosthesis in the whole system.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from app.domain.hand_spec import (
    ACTUATORS,
    DEFAULT_EMG_SAMPLE_RATE_HZ,
    DEFAULT_EMG_SAMPLES,
    DRIVEN_DOF,
    EMG_AMPLITUDE_MAX,
    EMG_AMPLITUDE_MIN,
    EMG_CHANNELS,
    EMG_CHANNEL_COUNT,
    EMG_CHANNEL_SITES,
    EMG_FEATURE_DOC,
    EMG_MATRIX_LAYOUT,
    FSR_COUNT,
    GESTURES,
    JOINTS,
    KINEMATIC_DOF,
    LIMIT_PROFILES,
    POTENTIOMETER_COUNT,
    PROTOCOL,
    SAFETY,
)
from app.domain.kinematics import actuator_joint_map
from app.schemas.api import HandSpecOut
from app.schemas.llm_output import llm_json_schema

router = APIRouter(prefix="/hand", tags=["hand"])


@router.get("/spec", response_model=HandSpecOut, summary="Full HANDi EPN V3 specification")
async def get_hand_spec() -> HandSpecOut:
    return HandSpecOut(
        driven_dof=DRIVEN_DOF,
        kinematic_dof=KINEMATIC_DOF,
        potentiometer_count=POTENTIOMETER_COUNT,
        fsr_count=FSR_COUNT,
        actuators=[
            {
                "letter": actuator.value,
                "label": spec.label,
                "digit": spec.digit.value,
                "description": spec.description,
                "hardware": spec.hardware,
                "motor_shield_terminal": spec.motor_shield_terminal,
                "joints": list(spec.joints),
            }
            for actuator, spec in ACTUATORS.items()
        ],
        joints=[
            {
                "id": j.id,
                "digit": j.digit.value,
                "joint_type": j.joint_type.value,
                "driven_by": j.driven_by.value,
                "min_flexion_deg": j.min_flexion_deg,
                "max_flexion_deg": j.max_flexion_deg,
                "coupling": j.coupling,
                "has_potentiometer": j.has_potentiometer,
                "axis": j.axis,
            }
            for j in JOINTS
        ],
        gestures=[
            {
                "command": command.value,
                "name": gesture.name,
                "description": gesture.description,
                "safety_class": gesture.safety_class.value,
                "pose": {a.value: v for a, v in (gesture.pose or {}).items()} or None,
                "typical_duration_ms": gesture.typical_duration_ms,
            }
            for command, gesture in GESTURES.items()
        ],
        limit_profiles=[
            {
                "id": profile.id.value,
                "label": profile.label,
                "source": profile.source,
                "notes": profile.notes,
                "limits": {a.value: list(bounds) for a, bounds in profile.limits.items()},
            }
            for profile in LIMIT_PROFILES.values()
        ],
        protocol=asdict(PROTOCOL),
        safety=asdict(SAFETY),
        emg={
            "channel_count": EMG_CHANNEL_COUNT,
            "channels": list(EMG_CHANNELS),
            "sites": dict(EMG_CHANNEL_SITES),
            "features": dict(EMG_FEATURE_DOC),
            "matrix_layout": EMG_MATRIX_LAYOUT,
            "amplitude_min": EMG_AMPLITUDE_MIN,
            "amplitude_max": EMG_AMPLITUDE_MAX,
            "default_samples": DEFAULT_EMG_SAMPLES,
            "default_sample_rate_hz": DEFAULT_EMG_SAMPLE_RATE_HZ,
        },
    )


@router.get("/actuator-joint-map", summary="Actuator letter -> driven joint ids")
async def get_actuator_joint_map() -> dict[str, list[str]]:
    return actuator_joint_map()


@router.get("/output-schema", summary="JSON Schema the LLM must satisfy")
async def get_output_schema() -> dict:
    return llm_json_schema()
