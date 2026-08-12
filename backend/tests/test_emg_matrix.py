"""The EMG stimulus: an N x 8 matrix of normalised raw samples."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.hand_spec import EMG_CHANNELS, EMG_CHANNEL_COUNT
from app.schemas.emg import MAX_SAMPLES, MIN_SAMPLES, EmgSourceMode, EmgWindow
from app.services import emg_features
from app.services.emg_service import (
    SYNTHETIC_GESTURES,
    MatrixParseError,
    blank_window,
    matrix_to_csv,
    parse_matrix_text,
    synthesise_window,
    window_checksum,
)


def flat_matrix(rows: int, value: float = 0.1) -> list[list[float]]:
    return [[value] * EMG_CHANNEL_COUNT for _ in range(rows)]


# ── Shape contract ──────────────────────────────────────────────────────────


def test_window_accepts_n_by_eight():
    window = EmgWindow(samples=flat_matrix(200))
    assert window.sample_count == 200
    assert len(window.samples[0]) == EMG_CHANNEL_COUNT


def test_window_ms_is_derived_from_rows_and_rate():
    window = EmgWindow(samples=flat_matrix(200), sample_rate_hz=1000)
    assert window.window_ms == 200.0
    faster = EmgWindow(samples=flat_matrix(200), sample_rate_hz=2000)
    assert faster.window_ms == 100.0


@pytest.mark.parametrize("columns", [1, 4, 7, 9, 16])
def test_wrong_column_count_is_rejected(columns):
    with pytest.raises(ValidationError, match="columns"):
        EmgWindow(samples=[[0.1] * columns for _ in range(10)])


def test_ragged_matrix_is_rejected():
    matrix = flat_matrix(5)
    matrix[3] = [0.1] * 6
    with pytest.raises(ValidationError, match="Row 3"):
        EmgWindow(samples=matrix)


def test_too_few_rows_is_rejected():
    with pytest.raises(ValidationError, match="at least"):
        EmgWindow(samples=flat_matrix(MIN_SAMPLES - 1))


def test_too_many_rows_is_rejected():
    with pytest.raises(ValidationError, match="exceeds"):
        EmgWindow(samples=flat_matrix(MAX_SAMPLES + 1))


@pytest.mark.parametrize("value", [1.5, -109.0, 512.0, 4095.0])
def test_raw_converter_values_are_accepted_unchanged(value):
    """No preprocessing: the matrix reaches the model in the units the hardware
    produced, so nothing between the electrode and the prompt can alter what the
    model is judged on."""
    window = EmgWindow(samples=[[value] * EMG_CHANNEL_COUNT for _ in range(10)])
    assert window.samples[0][0] == value


@pytest.mark.parametrize("value", [1e7, -1e7])
def test_absurd_values_are_still_rejected(value):
    """The remaining bound catches corruption, not measurement."""
    with pytest.raises(ValidationError):
        EmgWindow(samples=[[value] * EMG_CHANNEL_COUNT for _ in range(10)])


# ── Derived features ────────────────────────────────────────────────────────


def test_supplied_features_are_ignored_and_recomputed():
    """A caller cannot inject a feature vector that contradicts the signal.

    ``features`` is output-only, so a serialised window round-trips cleanly, but
    whatever the caller sends is discarded and re-derived from the matrix.
    """
    window = EmgWindow.model_validate({
        "samples": flat_matrix(10, 0.4),
        "features": [{"label": "CH1", "rms": 999.0, "mav": 999.0, "zc": 0,
                      "ssc": 0, "wl": 0.0, "min": 0.0, "max": 0.0, "variance": 0.0}],
    })
    assert window.features[0].rms == pytest.approx(0.4, abs=1e-6)
    assert len(window.features) == EMG_CHANNEL_COUNT


def test_a_serialised_window_can_be_submitted_back_unchanged():
    """The API returns computed fields; posting that object back must work."""
    original = synthesise_window("power_grasp", seed=2, samples=20)
    restored = EmgWindow.model_validate(original.model_dump(mode="json"))
    assert restored.samples == original.samples
    assert restored.sample_count == original.sample_count


def test_genuinely_unknown_keys_are_still_rejected():
    with pytest.raises(ValidationError):
        EmgWindow.model_validate({"samples": flat_matrix(10), "sampels": 1})


def test_one_feature_row_per_channel_in_order():
    window = EmgWindow(samples=flat_matrix(64))
    assert [f.label for f in window.features] == list(EMG_CHANNELS)


def test_rms_of_a_constant_signal_equals_its_magnitude():
    window = EmgWindow(samples=flat_matrix(50, 0.4))
    assert window.features[0].rms == pytest.approx(0.4, abs=1e-6)
    assert window.features[0].mav == pytest.approx(0.4, abs=1e-6)


def test_constant_signal_has_no_crossings_or_length():
    window = EmgWindow(samples=flat_matrix(50, 0.4))
    assert window.features[0].zc == 0
    assert window.features[0].ssc == 0
    assert window.features[0].wl == pytest.approx(0.0, abs=1e-9)


def test_alternating_signal_maximises_zero_crossings():
    matrix = [[0.5 if n % 2 == 0 else -0.5] * EMG_CHANNEL_COUNT for n in range(100)]
    window = EmgWindow(samples=matrix)
    assert window.features[0].zc == 99


def test_the_deadband_is_relative_to_the_signal_and_not_absolute():
    """It has to scale with the signal.

    The units are now whatever the converter produces, so a fixed threshold
    would count every noise crossing on a low-gain channel and suppress real
    ones on a high-gain channel. A deadband proportional to RMS makes the count
    invariant to gain, which is what lets two recordings be compared.
    """
    small = [0.5 if n % 2 == 0 else -0.5 for n in range(200)]
    large = [500.0 if n % 2 == 0 else -500.0 for n in range(200)]

    assert emg_features.zero_crossings(small) == emg_features.zero_crossings(large) == 199

    # A single large excursion in an otherwise quiet channel is one crossing,
    # not two hundred, at either scale.
    quiet_small = [0.001 * (1 if n % 2 == 0 else -1) for n in range(200)]
    quiet_small[100] = 1.0
    quiet_large = [v * 1000 for v in quiet_small]
    assert emg_features.zero_crossings(quiet_small) == emg_features.zero_crossings(quiet_large)


def test_channels_are_read_down_columns_not_across_rows():
    """Guards the layout: column c must be electrode c, for every row."""
    matrix = [[0.1 * (c + 1) for c in range(EMG_CHANNEL_COUNT)] for _ in range(20)]
    window = EmgWindow(samples=matrix)
    for index, feature in enumerate(window.features):
        assert feature.rms == pytest.approx(0.1 * (index + 1), abs=1e-6)


def test_group_activations_split_flexor_from_extensor():
    matrix = [[0.6, 0.6, 0.6, 0.6, 0.1, 0.1, 0.1, 0.3] for _ in range(30)]
    window = EmgWindow(samples=matrix)
    assert window.flexor_activation == pytest.approx(0.6, abs=1e-6)
    assert window.extensor_activation == pytest.approx(0.1, abs=1e-6)


# ── Parsing pasted matrices ─────────────────────────────────────────────────


def test_csv_round_trip_skips_the_header():
    """`CH1,CH2,...` must not be read as the data row [1, 2, ..., 8]."""
    original = synthesise_window("power_grasp", seed=3, samples=12).samples
    parsed = parse_matrix_text(matrix_to_csv(original))
    assert len(parsed) == 12
    assert parsed[0][0] == pytest.approx(original[0][0], abs=1e-4)


def test_json_array_is_accepted():
    parsed = parse_matrix_text("[[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8],"
                               "[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8]]")
    assert len(parsed) == 2


def test_json_object_with_samples_key_is_accepted():
    parsed = parse_matrix_text('{"samples": [[0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0]]}')
    assert len(parsed) == 2


def test_whitespace_and_bracket_noise_are_tolerated():
    text = "  [0.1  0.2  0.3  0.4  0.5  0.6  0.7  0.8]  \n[0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8]"
    assert len(parse_matrix_text(text)) == 2


def test_transposed_input_is_named_explicitly():
    text = "\n".join(",".join("0.1" for _ in range(200)) for _ in range(8))
    with pytest.raises(MatrixParseError, match="transposed"):
        parse_matrix_text(text)


def test_parsing_preserves_source_units():
    """Values pass through untouched - that is the whole point."""
    matrix = parse_matrix_text("1500,-900,300,120,80,-40,25,10\n" * 5)
    assert matrix[0] == [1500.0, -900.0, 300.0, 120.0, 80.0, -40.0, 25.0, 10.0]


def test_zero_indexed_headers_are_skipped():
    """Acquisition tools emit CH0..CH7 as readily as CH1..CH8."""
    text = "CH0,CH1,CH2,CH3,CH4,CH5,CH6,CH7\n" + "0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8\n" * 6
    matrix = parse_matrix_text(text)
    assert len(matrix) == 6
    assert matrix[0][0] == 0.1


# ── Synthetic stimuli ───────────────────────────────────────────────────────


@pytest.mark.parametrize("gesture", SYNTHETIC_GESTURES)
def test_every_synthetic_gesture_produces_a_valid_window(gesture):
    window = synthesise_window(gesture, seed=1)
    assert window.source_mode is EmgSourceMode.SYNTHETIC
    assert window.ground_truth_gesture == gesture
    assert window.sample_count == 200


def test_synthetic_signal_never_rails():
    """Hard clipping would flatten every peak and corrupt ZC/SSC.

    The generator now emits converter counts, so saturation is at 512 rather
    than 1.0.
    """
    for gesture in SYNTHETIC_GESTURES:
        window = synthesise_window(gesture, seed=5)
        for feature in window.features:
            assert abs(feature.min) < 512.0
            assert abs(feature.max) < 512.0


def test_rest_is_an_order_of_magnitude_quieter_than_activity():
    """Absolute thresholds no longer apply, so rest is defined by contrast."""
    rest = synthesise_window("rest", seed=5)
    grasp = synthesise_window("power_grasp", seed=5)
    assert grasp.total_activation > rest.total_activation * 5


def test_the_flexor_ratio_separates_the_gestures_without_a_scale():
    """The quantity the model is told to use. It must work without knowing the
    gain, which is exactly what removing normalisation demands of it."""
    assert synthesise_window("power_grasp", seed=5).flexor_ratio > 0.65
    assert synthesise_window("hand_open", seed=5).flexor_ratio < 0.35
    assert 0.35 < synthesise_window("co_contraction", seed=5).flexor_ratio < 0.65


def test_the_flexor_ratio_is_invariant_to_gain():
    window = synthesise_window("power_grasp", seed=5)
    amplified = EmgWindow(
        samples=[[v * 4 for v in row] for row in window.samples],
        sample_rate_hz=window.sample_rate_hz,
    )
    assert amplified.flexor_ratio == pytest.approx(window.flexor_ratio, abs=0.02)


def test_grasp_is_flexor_dominant_and_open_is_extensor_dominant():
    grasp = synthesise_window("power_grasp", seed=5)
    assert grasp.flexor_activation > grasp.extensor_activation * 2

    opening = synthesise_window("hand_open", seed=5)
    assert opening.extensor_activation > opening.flexor_activation * 2


def test_co_contraction_activates_both_groups():
    window = synthesise_window("co_contraction", seed=5)
    assert window.flexor_activation > 0.2
    assert window.extensor_activation > 0.2


def test_seed_makes_the_stimulus_reproducible():
    a = synthesise_window("power_grasp", seed=99)
    b = synthesise_window("power_grasp", seed=99)
    assert a.samples == b.samples
    assert window_checksum(a) == window_checksum(b)


def test_different_seeds_give_different_signals():
    a = synthesise_window("power_grasp", seed=1)
    b = synthesise_window("power_grasp", seed=2)
    assert a.samples != b.samples


def test_unknown_gesture_is_rejected():
    with pytest.raises(ValueError, match="Unknown synthetic gesture"):
        synthesise_window("levitate")


# ── Content addressing ──────────────────────────────────────────────────────


def test_checksum_ignores_provenance_but_not_signal():
    matrix = synthesise_window("point", seed=4).samples
    manual = EmgWindow(samples=matrix, source_mode=EmgSourceMode.MANUAL)
    live = EmgWindow(samples=matrix, source_mode=EmgSourceMode.LIVE, notes="from hardware")
    assert window_checksum(manual) == window_checksum(live)

    perturbed = [list(row) for row in matrix]
    perturbed[0][0] += 0.01
    assert window_checksum(EmgWindow(samples=perturbed)) != window_checksum(manual)


def test_checksum_tracks_the_sampling_rate():
    matrix = flat_matrix(20)
    a = EmgWindow(samples=matrix, sample_rate_hz=1000)
    b = EmgWindow(samples=matrix, sample_rate_hz=2000)
    assert window_checksum(a) != window_checksum(b)


def test_blank_window_is_all_zero():
    window = blank_window(samples=32)
    assert window.sample_count == 32
    assert window.total_activation == 0.0


# ── Decimation ──────────────────────────────────────────────────────────────


def test_downsample_uses_a_uniform_stride():
    matrix = [[float(n)] * EMG_CHANNEL_COUNT for n in range(100)]
    rows, factor = emg_features.downsample(matrix, 10)
    assert factor == 10
    assert [row[0] for row in rows] == [0.0, 10.0, 20.0, 30.0, 40.0,
                                        50.0, 60.0, 70.0, 80.0, 90.0]


def test_short_windows_are_not_decimated():
    matrix = flat_matrix(50)
    rows, factor = emg_features.downsample(matrix, 256)
    assert factor == 1
    assert len(rows) == 50


# ── No preprocessing ────────────────────────────────────────────────────────


def test_a_file_reaches_the_analysis_unmodified():
    """Nothing between the electrode and the analysis alters the samples.

    The claim is narrower than it was. The file no longer reaches the *prompt*
    unmodified — the whole point of the current flow is that it is filtered,
    rectified, smoothed and drawn. What must still hold is that loading changes
    nothing: every transformation the model is judged on happens inside
    `analyse`, where it is recorded, and none of it happens in the parser.
    """
    from pathlib import Path

    from app.services.analysis_service import FeatureSource, analyse

    fixture = Path(__file__).parent / "fixtures" / "apertura_mano_muestra_02.csv"
    matrix = parse_matrix_text(fixture.read_text())
    window = EmgWindow(samples=matrix, sample_rate_hz=1000)

    assert window.samples == matrix

    # With preprocessing off, nothing is computed between the file and the
    # picture: no envelope exists, and the filter metadata is empty rather than
    # describing a chain that never ran.
    raw = analyse(
        window.samples,
        sample_rate_hz=window.sample_rate_hz,
        feature_source=FeatureSource.RAW,
    )
    assert raw.envelope is None
    assert raw.preprocessing == {}


def test_features_are_reported_in_acquisition_units():
    matrix = [[100.0] * EMG_CHANNEL_COUNT for _ in range(20)]
    window = EmgWindow(samples=matrix)
    assert window.features[0].rms == pytest.approx(100.0)


def test_a_utf8_bom_does_not_turn_the_header_into_data():
    """Excel and several acquisition tools prepend a BOM, and it is invisible.

    Without stripping it the header stops matching the label pattern, so
    `CH0,CH1,...,CH7` parses as the perfectly-shaped data row [0,1,...,7] and a
    fabricated first sample enters the window with nothing to signal it.
    """
    body = "CH0,CH1,CH2,CH3,CH4,CH5,CH6,CH7\n" + "-2,-2,-3,-3,0,2,0,0\n" * 10

    plain = parse_matrix_text(body)
    with_bom = parse_matrix_text("﻿" + body)

    assert with_bom == plain
    assert len(with_bom) == 10
    assert with_bom[0] != [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]


def test_windows_line_endings_are_handled():
    body = "CH0,CH1,CH2,CH3,CH4,CH5,CH6,CH7\r\n" + "-2,-2,-3,-3,0,2,0,0\r\n" * 5
    assert len(parse_matrix_text(body)) == 5
