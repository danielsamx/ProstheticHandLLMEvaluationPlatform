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
    """The recording becomes a picture and eight rows of descriptors.

    It used to become 404 printed rows of samples. The assertion changed with
    the flow, and the interesting property changed with it: the size of the user
    turn no longer depends on the length of the recording at all.
    """
    window = EmgWindow(samples=raw_matrix, sample_rate_hz=1000,
                       ground_truth_gesture="hand_open")
    prompt = build_prompt(window, handedness=Handedness.RIGHT)

    block = prompt.dynamic_prompt
    assert block.startswith("DERIVED FEATURES")
    # Eight channels, one row each — whatever the recording's length.
    assert sum(line.startswith("CH") for line in block.splitlines()) == EMG_CHANNEL_COUNT

    # No sample survives into the text: the matrix is not printed anywhere.
    assert "[-2.000" not in prompt.full_prompt

    # The picture is the stimulus, and it travels in the user turn.
    assert prompt.image_data_url is not None
    assert prompt.image_sha256
    user_turn = prompt.messages[-1]["content"]
    assert any(part.get("type") == "image_url" for part in user_turn)


def test_a_real_recording_now_fits_a_small_context(raw_matrix):
    """404 rows of real acquisition used not to fit an 8k context.

    They do now, because they are not sent: the model is shown a picture and
    eight rows of descriptors. This is the flow's most concrete consequence, and
    it is worth pinning — if a change ever puts samples back into the text, the
    budget will notice before a researcher does.

    The estimate covers text only. The picture also occupies context, at a rate
    that depends on the vision encoder, so "fits" here means the text fits.
    """
    from app.prompts.budget import check

    window = EmgWindow(samples=raw_matrix, sample_rate_hz=1000)
    prompt = build_prompt(window)

    report = check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        emg_context=prompt.emg_context,
        image_context=prompt.image_context,
        context_window=8192,
    )
    assert report.fits, report.summary()

    # And the size no longer tracks the recording: a window ten times shorter
    # produces a user turn of the same shape.
    short = build_prompt(EmgWindow(samples=raw_matrix[:40], sample_rate_hz=1000))
    assert len(short.dynamic_prompt.splitlines()) == len(prompt.dynamic_prompt.splitlines())
