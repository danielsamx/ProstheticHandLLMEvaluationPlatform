import numpy as np

from app.services.myo_preprocessing import preprocess


def test_myo_pipeline_preserves_shape_and_bounds_normalised_signal():
    t = np.arange(200) / 200
    samples = np.stack([30 + 20 * np.sin(2 * np.pi * (25 + i) * t) for i in range(8)], axis=1)
    processed, metadata = preprocess(samples.tolist(), sample_rate_hz=200, normalisation="max_abs")
    result = np.asarray(processed)
    assert result.shape == (200, 8)
    assert np.max(np.abs(result)) <= 1.000001
    assert metadata["pipeline_version"] == "myo-v1"


def test_channel_order_is_validated():
    try:
        preprocess([[0] * 8 for _ in range(32)], sample_rate_hz=200,
                   channel_order=[0, 0, 1, 2, 3, 4, 5, 6])
    except ValueError as exc:
        assert "permutation" in str(exc)
    else:
        raise AssertionError("invalid channel map accepted")
