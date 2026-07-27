"""EMG helpers: blank matrix, paste parsing, synthetic stimuli, stored windows."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain.hand_spec import (
    EMG_AMPLITUDE_MAX,
    EMG_AMPLITUDE_MIN,
    EMG_CHANNELS,
    EMG_CHANNEL_COUNT,
    EMG_CHANNEL_SITES,
    EMG_MATRIX_LAYOUT,
)
from app.models.emg import EmgWindowRecord
from app.schemas.emg import (
    MAX_SAMPLES,
    MIN_SAMPLES,
    EmgSourceMode,
    EmgWindow,
    MatrixParseRequest,
    MatrixParseResponse,
)
from app.services import emg_service
from app.services.emg_features import NormalisationMode

router = APIRouter(prefix="/emg", tags=["emg"])


@router.get("/format", summary="The matrix contract the UI must satisfy")
async def matrix_format() -> dict:
    return {
        "channel_count": EMG_CHANNEL_COUNT,
        "channels": list(EMG_CHANNELS),
        "sites": dict(EMG_CHANNEL_SITES),
        "layout": EMG_MATRIX_LAYOUT,
        "amplitude_min": EMG_AMPLITUDE_MIN,
        "amplitude_max": EMG_AMPLITUDE_MAX,
        "min_rows": MIN_SAMPLES,
        "max_rows": MAX_SAMPLES,
        "normalisation_modes": [m.value for m in NormalisationMode],
        "header_note": "A label-only first line is skipped, whether it reads "
                       "CH0..CH7 or CH1..CH8.",
    }


@router.get("/blank", response_model=EmgWindow, summary="Zeroed N x 8 matrix")
async def blank_window(
    mode: EmgSourceMode = EmgSourceMode.MANUAL,
    samples: int = Query(default=64, ge=MIN_SAMPLES, le=MAX_SAMPLES),
) -> EmgWindow:
    return emg_service.blank_window(mode, samples=samples)


@router.post("/parse", response_model=MatrixParseResponse, summary="Parse a pasted matrix")
async def parse_matrix(payload: MatrixParseRequest) -> MatrixParseResponse:
    """Read an N x 8 matrix out of pasted CSV, TSV, whitespace or JSON text.

    Permissive about delimiters and about header labels - acquisition tools
    emit CH0..CH7 as readily as CH1..CH8, and the header is skipped by shape
    rather than by matching specific names. Strict about the matrix itself: a
    silently transposed matrix would corrupt every derived feature, so that
    case is detected and named explicitly rather than accepted.

    The response reports the divisor that was applied, because how amplitudes
    were normalised determines whether two windows can be compared at all.
    """
    try:
        raw = emg_service.parse_matrix_text(payload.text)
        matrix, report = emg_service.normalise_matrix(
            raw, payload.normalisation, payload.full_scale
        )
    except emg_service.MatrixError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    try:
        window = EmgWindow(
            samples=matrix,
            source_mode=EmgSourceMode.MANUAL,
            sample_rate_hz=payload.sample_rate_hz,
            ground_truth_gesture=payload.ground_truth_gesture,
            notes=(
                f"Imported matrix, {payload.normalisation.value} normalisation "
                f"(divisor {report.divisor:g}, source peak {report.observed_peak:g})."
            ),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return MatrixParseResponse(
        window=window,
        normalisation=report.mode,
        observed_peak=report.observed_peak,
        divisor=report.divisor,
        inferred_full_scale=report.inferred_full_scale,
        warnings=report.warnings,
    )


@router.get("/synthetic/gestures", response_model=list[str])
async def synthetic_gestures() -> list[str]:
    return list(emg_service.SYNTHETIC_GESTURES)


@router.get("/synthetic", response_model=EmgWindow)
async def synthesise(
    gesture: str,
    noise: float = Query(default=0.12, ge=0.0, le=0.6),
    samples: int = Query(default=200, ge=MIN_SAMPLES, le=2_000),
    seed: int | None = None,
) -> EmgWindow:
    """Generate a labelled raw matrix with a known ground truth.

    Because the label is known, gesture accuracy is scored automatically
    instead of relying on manual annotation.
    """
    try:
        return emg_service.synthesise_window(gesture, noise=noise, seed=seed, samples=samples)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/windows/{window_id}", response_model=EmgWindow)
async def get_window(window_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    record = await session.get(EmgWindowRecord, window_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "EMG window not found.")
    return emg_service.record_to_window(record)


@router.get("/windows/{window_id}/csv", response_model=dict)
async def export_window_csv(
    window_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    record = await session.get(EmgWindowRecord, window_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "EMG window not found.")
    return {"filename": f"emg_{window_id}.csv",
            "csv": emg_service.matrix_to_csv(record.samples)}


@router.get("/windows", response_model=list[dict])
async def list_windows(
    source_mode: EmgSourceMode | None = None,
    ground_truth_gesture: str | None = None,
    limit: int = Query(default=50, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(EmgWindowRecord).order_by(EmgWindowRecord.created_at.desc()).limit(limit)
    if source_mode:
        stmt = stmt.where(EmgWindowRecord.source_mode == source_mode.value)
    if ground_truth_gesture:
        stmt = stmt.where(EmgWindowRecord.ground_truth_gesture == ground_truth_gesture)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "source_mode": r.source_mode,
            "sample_count": r.sample_count,
            "window_ms": r.window_ms,
            "mean_rms": r.mean_rms,
            "ground_truth_gesture": r.ground_truth_gesture,
            "checksum": r.checksum,
            "captured_at": r.captured_at,
            "session_id": r.session_id,
            "sequence": r.sequence,
        }
        for r in rows
    ]
