from fastapi import APIRouter, Depends

from app.core.security import Permission, require_permission
from app.models.user import User
from app.schemas.emg import EmgSourceMode, EmgWindow
from app.schemas.myo import MyoPreprocessIn, MyoPreprocessOut
from app.services.myo_preprocessing import preprocess

router = APIRouter(prefix="/myo", tags=["myo"])


@router.post("/preprocess", response_model=MyoPreprocessOut)
async def preprocess_myo(payload: MyoPreprocessIn,
                         _: User = Depends(require_permission(Permission.MANAGE_MYO))):
    processed, metadata = preprocess(
        payload.samples, sample_rate_hz=payload.sample_rate_hz,
        channel_order=payload.channel_order, calibration_scale=payload.calibration_scale,
        remove_dc=payload.remove_dc, notch_hz=payload.notch_hz,
        bandpass_low_hz=payload.bandpass_low_hz,
        bandpass_high_hz=payload.bandpass_high_hz, rectify=payload.rectify,
        envelope_ms=payload.envelope_ms, normalisation=payload.normalisation,
    )
    common = dict(source_mode=EmgSourceMode.LIVE, sample_rate_hz=payload.sample_rate_hz,
                  ground_truth_gesture=payload.ground_truth_gesture)
    return MyoPreprocessOut(
        raw_window=EmgWindow(samples=payload.samples, notes="Myo raw", **common),
        processed_window=EmgWindow(samples=processed, notes="Myo preprocessed: myo-v1", **common),
        metadata=metadata,
    )
