"""End-to-end over a real acquisition file.

Guards the exact shape the researcher's hardware produces: a `CH0..CH7` header,
404 rows of signed integer converter counts. Every earlier bug in this path -
the header parsed as data, the transposed-matrix trap, the amplitude range -
would have been caught here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.hand_spec import EMG_CHANNEL_COUNT, Handedness
from app.prompts.builder import build_prompt
from app.schemas.emg import EmgWindow
from app.services.emg_features import NormalisationError, NormalisationMode, normalise_matrix
from app.services.emg_service import parse_matrix_text, window_checksum

FIXTURE = Path(__file__).parent / "fixtures" / "apertura_mano_muestra_02.csv"


@pytest.fixture(scope="module")
def raw_matrix() -> list[list[float]]:
    return parse_matrix_text(FIXTURE.read_text())


def test_file_parses_to_the_expected_shape(raw_matrix):
    assert len(raw_matrix) == 404
    assert all(len(row) == EMG_CHANNEL_COUNT for row in raw_matrix)


def test_zero_indexed_header_is_not_read_as_data(raw_matrix):
    """`CH0,CH1,…,CH7` would parse as the row [0, 1, …, 7] if the header were
    matched by number extraction rather than by shape."""
    assert raw_matrix[0] != [float(i) for i in range(EMG_CHANNEL_COUNT)]
    assert raw_matrix[0] == [-2.0, -2.0, -3.0, -3.0, 0.0, 2.0, 0.0, 0.0]


def test_values_are_signed_converter_counts(raw_matrix):
    flat = [v for row in raw_matrix for v in row]
    assert min(flat) == -109.0
    assert max(flat) == 106.0
    assert all(v == int(v) for v in flat)


def test_raw_counts_are_refused_without_a_normalisation_choice(raw_matrix):
    with pytest.raises(NormalisationError, match="raw converter counts"):
        normalise_matrix(raw_matrix, NormalisationMode.NONE)


def test_declared_full_scale_produces_a_valid_window(raw_matrix):
    matrix, report = normalise_matrix(raw_matrix, NormalisationMode.FULL_SCALE, 512)
    window = EmgWindow(samples=matrix, sample_rate_hz=1000)

    assert report.divisor == 512
    assert window.sample_count == 404
    assert window.window_ms == 404.0
    assert all(abs(v) <= 1.0 for row in window.samples for v in row)


def test_the_recording_is_flexor_dominant(raw_matrix):
    """Whatever the divisor, the balance between electrode groups is preserved -
    it is the ratio, not the absolute level, that identifies the gesture."""
    matrix, _ = normalise_matrix(raw_matrix, NormalisationMode.FULL_SCALE, 512)
    window = EmgWindow(samples=matrix, sample_rate_hz=1000)
    assert window.flexor_activation > window.extensor_activation * 2


def test_full_scale_choice_moves_the_activation_reading(raw_matrix):
    """Documents a real calibration trap.

    The technical context tells the model that a mean RMS below 0.10 means rest.
    With this file, a full scale of 512 puts the window under that threshold and
    a full scale of 128 puts it over - so the declared full scale has to match
    the hardware, or the model is told 'rest' about a recording of movement.
    """
    wide, _ = normalise_matrix(raw_matrix, NormalisationMode.FULL_SCALE, 512)
    tight, _ = normalise_matrix(raw_matrix, NormalisationMode.FULL_SCALE, 128)

    assert EmgWindow(samples=wide).total_activation < 0.10
    assert EmgWindow(samples=tight).total_activation > 0.10


def test_checksum_changes_with_the_normalisation(raw_matrix):
    a, _ = normalise_matrix(raw_matrix, NormalisationMode.FULL_SCALE, 512)
    b, _ = normalise_matrix(raw_matrix, NormalisationMode.FULL_SCALE, 128)
    assert window_checksum(EmgWindow(samples=a)) != window_checksum(EmgWindow(samples=b))


def test_the_window_renders_into_a_prompt(raw_matrix):
    matrix, _ = normalise_matrix(raw_matrix, NormalisationMode.FULL_SCALE, 512)
    window = EmgWindow(samples=matrix, sample_rate_hz=1000, ground_truth_gesture="hand_open")
    prompt = build_prompt(window, handedness=Handedness.RIGHT)

    block = prompt.dynamic_prompt
    assert "404 samples @ 1000 Hz" in block
    # 404 rows exceeds the 256-row print budget, so it is decimated and labelled.
    assert "every 2nd row is shown" in block
    assert "computed from the complete window" in block
    for index in range(1, 9):
        assert f"| CH{index} |" in block


def test_prompt_stays_within_a_reasonable_context_budget(raw_matrix):
    matrix, _ = normalise_matrix(raw_matrix, NormalisationMode.FULL_SCALE, 512)
    prompt = build_prompt(EmgWindow(samples=matrix, sample_rate_hz=1000))
    # ~4 chars per token: this must leave room in a 16k-token window.
    assert prompt.char_counts()["total"] < 40_000
