"""Derivation of the scientific metrics stored per execution."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from app.domain.hand_spec import GESTURES, Actuator, ControlCommand
from app.domain.kinematics import HandPose, pose_from_gesture
from app.schemas.emg import EmgWindow
from app.schemas.llm_output import ProstheticCommand
from app.services.llm_service import LlmCallResult
from app.validation.results import ValidationReport, ValidationStage

#: Map a ground-truth label onto the firmware gesture it should produce.
GROUND_TRUTH_TO_GESTURE: dict[str, ControlCommand] = {
    "rest": ControlCommand.OPEN,
    "hand_open": ControlCommand.OPEN,
    "power_grasp": ControlCommand.CLOSE,
    "hand_close": ControlCommand.CLOSE,
    "precision_pinch": ControlCommand.PINCH,
    "pinch": ControlCommand.PINCH,
    "ok_sign": ControlCommand.OK,
    "thumbs_up": ControlCommand.THUMBS_UP,
    "point": ControlCommand.POINT,
    "pointing": ControlCommand.POINT,
    "call_me": ControlCommand.CALL_ME,
    "number_three": ControlCommand.NUMBER_THREE,
    "number_four": ControlCommand.NUMBER_FOUR,
    "spiderman": ControlCommand.SPIDERMAN,
    "partial_claw": ControlCommand.PARTIAL_CLAW,
    "co_contraction": ControlCommand.STOP,
    "stop": ControlCommand.STOP,
}


def response_fingerprint(parsed: dict[str, Any] | None) -> str | None:
    """Canonical digest of the parsed response.

    Identical fingerprints across repetitions at temperature 0 are direct
    evidence of determinism; divergence quantifies sampling instability.
    """
    if not parsed:
        return None
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _reference_pose(gesture: ControlCommand, handedness, profile) -> HandPose | None:
    return pose_from_gesture(gesture, handedness=handedness, profile=profile)


def _pose_distance(actual: HandPose, reference: HandPose) -> tuple[float, float]:
    """(MAE, similarity) between two poses in normalised actuator space."""
    keys = [a.value for a in Actuator]
    diffs = [
        abs(actual.actuator_normalised.get(k, 0.0) - reference.actuator_normalised.get(k, 0.0))
        for k in keys
    ]
    mae = sum(diffs) / len(keys)
    rms = math.sqrt(sum(d * d for d in diffs) / len(keys))
    return round(mae, 4), round(max(0.0, 1.0 - rms), 4)


def compute_metrics(
    *,
    report: ValidationReport,
    call: LlmCallResult | None,
    window: EmgWindow,
    handedness,
    profile,
    repetition_group: str | None = None,
) -> dict[str, Any]:
    """Build the ``execution_metrics`` payload for one execution."""
    command: ProstheticCommand | None = report.parsed_command
    parsed_dict = command.model_dump(mode="json") if command else None
    stages = set(report.stages_completed)

    metrics: dict[str, Any] = {
        # A recoverable command at all. Kept under the old column names so a
        # year of history stays queryable with one set of names.
        "is_valid_json": ValidationStage.PARSE in stages,
        # The reply was the bare command line, with nothing wrapped around it.
        # This is now the sharpest single measure of instruction adherence.
        "is_bare_json": ValidationStage.PARSE in stages
        and not any(i.code == "COMMAND_REQUIRED_REPAIR" for i in report.issues),
        # No separate schema stage exists: a well-formed command *is* the shape.
        "schema_compliant": ValidationStage.PROTOCOL in stages,
        "protocol_compliant": ValidationStage.PROTOCOL in stages,
        "within_mechanical_limits": ValidationStage.RANGE in stages
        and ValidationStage.KINEMATIC in stages,
        "safety_compliant": ValidationStage.SAFETY in stages,
        "ground_truth_gesture": window.ground_truth_gesture,
        "predicted_gesture": None,
        "gesture_correct": None,
        "detected_pattern": command.detected_pattern if command else None,
        "pose_mae": None,
        "pose_similarity": None,
        # The model no longer reports a confidence, so there is nothing to
        # calibrate. Recording a fabricated value would be worse than a null.
        "model_confidence": None,
        "calibration_error": None,
        "actuators_commanded": len(command.commands) if command else 0,
        "intent": command.intent if command else None,
        "used_preset_gesture": bool(command and command.intent in ("gesture", "stop")),
        # "Refusing" is now a real command: `O` holds the hand open. It is the
        # documented rest pose, so it is both a refusal and a safe action.
        "refused_to_act": bool(
            command and command.gesture == ControlCommand.OPEN.value
        ),
        "latency_ms": call.latency_ms if call else None,
        "tokens_per_second": call.tokens_per_second if call else None,
        "cost_usd": call.cost_usd if call else 0.0,
        "output_token_efficiency": None,
        "response_fingerprint": response_fingerprint(parsed_dict),
        "repetition_group": repetition_group,
        "extra": {
            "dropped_params": call.dropped_params if call else [],
            "finish_reason": call.finish_reason if call else None,
            "serial_command": report.normalised_serial,
            "mean_rms": round(window.total_activation, 4),
            "emg_source_mode": window.source_mode.value,
            "warning_codes": sorted({i.code for i in report.warnings}),
            "error_codes": sorted({i.code for i in report.errors}),
        },
    }

    # ── Predicted gesture label ─────────────────────────────────────────────
    if command is not None:
        if command.gesture:
            gesture = GESTURES.get(ControlCommand(command.gesture))
            metrics["predicted_gesture"] = gesture.name if gesture else command.gesture
        elif command.intent == "joint_positions":
            metrics["predicted_gesture"] = "CUSTOM_POSE"
        elif command.intent == "no_action":
            metrics["predicted_gesture"] = "NO_ACTION"

    # ── Accuracy against a labelled window ──────────────────────────────────
    truth_label = (window.ground_truth_gesture or "").strip().lower()
    truth_cmd = GROUND_TRUTH_TO_GESTURE.get(truth_label)
    if truth_cmd is not None and command is not None:
        expected_name = GESTURES[truth_cmd].name
        if command.gesture:
            metrics["gesture_correct"] = ControlCommand(command.gesture) is truth_cmd
        elif report.resolved_pose is not None:
            reference = _reference_pose(truth_cmd, handedness, profile)
            if reference is not None:
                mae, similarity = _pose_distance(report.resolved_pose, reference)
                metrics["pose_mae"] = mae
                metrics["pose_similarity"] = similarity
                # A custom pose counts as correct when it lands close to the
                # canonical target pose (<= 0.15 mean normalised error).
                metrics["gesture_correct"] = mae <= 0.15
        else:
            metrics["gesture_correct"] = False
        metrics["extra"]["expected_gesture_name"] = expected_name

    # ── Output efficiency ───────────────────────────────────────────────────
    # Useful characters per completion token. With a two-character reply the
    # ideal is close to 1; a model spending fifty tokens to say `C` is
    # measurably wasteful, and this is where that shows.
    if call and call.completion_tokens:
        useful = len(report.normalised_serial or "")
        metrics["output_token_efficiency"] = round(useful / call.completion_tokens, 4)

    return metrics


def aggregate_determinism(fingerprints: list[str | None]) -> dict[str, Any]:
    """Determinism statistics for a group of repeated executions."""
    valid = [f for f in fingerprints if f]
    if not valid:
        return {"repetitions": len(fingerprints), "distinct_responses": 0, "determinism_rate": None}
    counts: dict[str, int] = {}
    for f in valid:
        counts[f] = counts.get(f, 0) + 1
    modal = max(counts.values())
    return {
        "repetitions": len(fingerprints),
        "valid_responses": len(valid),
        "distinct_responses": len(counts),
        "modal_frequency": modal,
        "determinism_rate": round(modal / len(valid), 4),
    }
