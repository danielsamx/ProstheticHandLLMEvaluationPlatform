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



def test_the_recording_is_flexor_dominant(raw_matrix):
    """The ratio, not the absolute level, identifies the gesture — which is why
    the matrix can be passed through unscaled."""
    window = EmgWindow(samples=raw_matrix, sample_rate_hz=1000)
    assert window.flexor_activation > window.extensor_activation * 2
    assert window.flexor_ratio > 0.65


def test_the_window_renders_into_a_prompt(raw_matrix):
    window = EmgWindow(samples=raw_matrix, sample_rate_hz=1000,
                       ground_truth_gesture="hand_open")
    prompt = build_prompt(window, handedness=Handedness.RIGHT)

    block = prompt.dynamic_prompt
    lines = block.splitlines()

    # The matrix and nothing else: no acquisition metadata, no feature table.
    assert all(ln.startswith("[") and ln.endswith("]") for ln in lines)
    assert all(ln.count(",") == 7 for ln in lines)

    # Every row of the imported recording, not an excerpt of it.
    assert len(lines) == window.sample_count == 404


def test_a_real_recording_needs_a_larger_context_and_the_budget_says_which(raw_matrix):
    """404 rows of real acquisition do not fit an 8k context.

    Previously they did, because only 32 of them were sent. Fitting was a
    property of the excerpt, not of the recording, and reporting the full row
    count beside a truncated prompt is the kind of quiet mismatch that survives
    into a published number.
    """
    from app.prompts.budget import check

    window = EmgWindow(samples=raw_matrix, sample_rate_hz=1000)
    prompt = build_prompt(window)

    small = check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        emg_context=prompt.emg_context,
        context_window=8192,
        matrix_rows=window.sample_count,
    )
    assert not small.fits
    assert any("context length" in line for line in small.advice)

    # The size the advice points at does hold it.
    large = check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        emg_context=prompt.emg_context,
        context_window=32768,
    )
    assert large.fits, large.summary()
