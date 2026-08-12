"""The envelope chain and the picture drawn from it.

Tested against synthetic signals whose correct answer is known by construction:
a gated broadband burst with mains interference and baseline drift added on top.
Real EMG cannot be used here, because a test whose expected output came from the
same code it is testing proves only that the code is deterministic.
"""

from __future__ import annotations

import math

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from app.domain.envelope import (  # noqa: E402
    BANDPASS_HIGH_HZ,
    MAINS_NOTCH_HZ,
    linear_envelope,
    usable_band,
)
from app.services import envelope_image  # noqa: E402

MYO_RATE_HZ = 200


def _window(
    flexor_gain: float,
    extensor_gain: float,
    *,
    rows: int = 600,
    rate: int = MYO_RATE_HZ,
    mains_amplitude: float = 2.0,
    seed: int = 7,
) -> list[list[float]]:
    """A gated burst plus the two artefacts the chain exists to remove."""
    rng = np.random.default_rng(seed)
    t = np.arange(rows) / rate

    gate = np.zeros(rows)
    gate[rows // 4 : (rows * 3) // 4] = 1.0
    gains = np.array([flexor_gain] * 4 + [extensor_gain] * 4)

    signal = rng.normal(0, 1, (rows, 8)) * gate[:, None] * gains
    signal += 0.6 * rng.normal(0, 1, (rows, 8))
    signal += mains_amplitude * np.sin(2 * np.pi * MAINS_NOTCH_HZ * t)[:, None]
    signal += 2.5 * np.sin(2 * np.pi * 1.5 * t)[:, None]
    return signal.tolist()


def _burst_contrast(envelope: list[list[float]]) -> float:
    """Mean amplitude during the burst over mean amplitude at rest."""
    data = np.asarray(envelope)
    rows = data.shape[0]
    active = data[rows // 4 + 20 : (rows * 3) // 4 - 20].mean()
    resting = np.r_[data[: rows // 4 - 20], data[(rows * 3) // 4 + 20 :]].mean()
    return float(active / resting)


class TestUsableBand:
    def test_a_myo_cannot_reach_the_canonical_upper_cutoff(self) -> None:
        """200 Hz sampling puts Nyquist at 100 Hz, so 450 Hz cannot exist.

        The clamp must be reported, not just applied. A window filtered at
        20-95 Hz and one filtered at 20-450 Hz are different signals, and a
        record that called them both "20-450" would make them look comparable.
        """
        low, high, clamped = usable_band(MYO_RATE_HZ)

        assert clamped is True
        assert high < BANDPASS_HIGH_HZ
        assert high < MYO_RATE_HZ / 2
        assert low == 20.0

    def test_a_thousand_hertz_reaches_it_unclamped(self) -> None:
        low, high, clamped = usable_band(1000)

        assert (low, high) == (20.0, BANDPASS_HIGH_HZ)
        assert clamped is False


class TestLinearEnvelope:
    def test_the_burst_stands_out_from_rest(self) -> None:
        result = linear_envelope(_window(6.0, 1.2), sample_rate_hz=MYO_RATE_HZ)

        assert _burst_contrast(result.samples) > 3.0

    def test_the_mains_notch_is_what_makes_the_burst_visible(self) -> None:
        """The finding that put the notch in the chain.

        At 1000 Hz, 60 Hz interference is one narrow component inside a 430 Hz
        band and the band-pass barely notices it. At 200 Hz the band is 20-95 Hz
        and 60 Hz sits in the middle of it, so the band-pass cannot reject it at
        all — the "resting" envelope is then mostly hum, and the contrast the
        model is asked to read collapses.
        """
        raw = _window(6.0, 1.2)

        with_notch = linear_envelope(raw, sample_rate_hz=MYO_RATE_HZ)
        without = linear_envelope(raw, sample_rate_hz=MYO_RATE_HZ, mains_notch_hz=None)

        assert _burst_contrast(with_notch.samples) > 2 * _burst_contrast(without.samples)

    def test_the_envelope_is_never_negative(self) -> None:
        """A magnitude below zero is meaningless, and would drop every plot floor.

        Zero-phase low-pass filtering undershoots at a sharp edge, so this is a
        real outcome of the chain rather than a hypothetical.
        """
        result = linear_envelope(_window(9.0, 0.5), sample_rate_hz=MYO_RATE_HZ)

        assert min(min(row) for row in result.samples) >= 0.0

    def test_a_flexor_window_and_an_extensor_window_are_distinguishable(self) -> None:
        """The whole premise: group balance survives the chain."""

        def flexor_share(samples: list[list[float]]) -> float:
            data = np.asarray(samples)
            flexor, extensor = data[:, :4].mean(), data[:, 4:].mean()
            return float(flexor / (flexor + extensor))

        closing = linear_envelope(_window(6.0, 1.2), sample_rate_hz=MYO_RATE_HZ)
        opening = linear_envelope(_window(1.2, 6.0), sample_rate_hz=MYO_RATE_HZ)

        assert flexor_share(closing.samples) > 0.65
        assert flexor_share(opening.samples) < 0.35

    def test_a_short_window_is_rectified_but_says_it_was_not_filtered(self) -> None:
        """filtfilt cannot run on a window shorter than its own padding.

        Returning a rectified signal and calling it an envelope would be the
        quiet failure; the metadata has to carry the difference.
        """
        result = linear_envelope(_window(6.0, 1.2, rows=40), sample_rate_hz=MYO_RATE_HZ)

        assert result.was_filtered is False
        assert any("rectified only" in note for note in result.metadata["notes"])

    def test_the_metadata_records_what_ran_not_what_was_asked_for(self) -> None:
        result = linear_envelope(_window(6.0, 1.2), sample_rate_hz=MYO_RATE_HZ)
        metadata = result.metadata

        assert metadata["requested_bandpass_hz"] == [20.0, BANDPASS_HIGH_HZ]
        assert metadata["applied_bandpass_hz"] != metadata["requested_bandpass_hz"]
        assert metadata["bandpass_clamped_to_nyquist"] is True
        assert metadata["zero_phase"] is True

    def test_a_cutoff_above_nyquist_is_refused_rather_than_silently_moved(self) -> None:
        with pytest.raises(ValueError, match="cannot be represented"):
            linear_envelope(
                _window(6.0, 1.2), sample_rate_hz=MYO_RATE_HZ, envelope_cutoff_hz=150.0
            )

    def test_a_matrix_that_is_not_eight_channels_is_refused(self) -> None:
        with pytest.raises(ValueError, match="N x 8"):
            linear_envelope([[0.0, 1.0, 2.0]] * 100, sample_rate_hz=MYO_RATE_HZ)


class TestEnvelopeImage:
    def test_two_renders_of_one_window_are_byte_identical(self) -> None:
        """Without this the stored image digest proves nothing.

        matplotlib writes the current time into PNG metadata by default, which
        alone would make every render unique and every digest meaningless.
        """
        envelope = linear_envelope(_window(6.0, 1.2), sample_rate_hz=MYO_RATE_HZ).samples

        first = envelope_image.render(envelope, sample_rate_hz=MYO_RATE_HZ)
        second = envelope_image.render(envelope, sample_rate_hz=MYO_RATE_HZ)

        assert first.sha256 == second.sha256
        assert first.png == second.png

    def test_different_windows_render_differently(self) -> None:
        """The companion check: identical digests must mean identical input."""
        closing = linear_envelope(_window(6.0, 1.2), sample_rate_hz=MYO_RATE_HZ).samples
        opening = linear_envelope(_window(1.2, 6.0), sample_rate_hz=MYO_RATE_HZ).samples

        assert (
            envelope_image.render(closing, sample_rate_hz=MYO_RATE_HZ).sha256
            != envelope_image.render(opening, sample_rate_hz=MYO_RATE_HZ).sha256
        )

    def test_the_amplitude_scale_is_shared_across_channels(self) -> None:
        """The decision most likely to be undone by someone tidying the plot.

        Per-channel scaling would draw a resting channel and a fully contracting
        one at the same height, destroying exactly the comparison the image
        exists to support. Asserted through the reported ceiling, which is
        computed once across every channel.
        """
        envelope = linear_envelope(_window(9.0, 0.4), sample_rate_hz=MYO_RATE_HZ).samples
        image = envelope_image.render(envelope, sample_rate_hz=MYO_RATE_HZ)

        peak = max(max(row) for row in envelope)

        assert image.metadata["shared_amplitude_scale"] is True
        assert image.metadata["amplitude_ceiling"] >= peak

    def test_it_is_a_png_carrying_its_own_identity(self) -> None:
        envelope = linear_envelope(_window(6.0, 1.2), sample_rate_hz=MYO_RATE_HZ).samples
        image = envelope_image.render(envelope, sample_rate_hz=MYO_RATE_HZ)

        assert image.png.startswith(b"\x89PNG\r\n\x1a\n")
        assert image.data_url.startswith("data:image/png;base64,")
        assert len(image.sha256) == 64

    def test_the_time_axis_follows_the_sample_rate(self) -> None:
        envelope = linear_envelope(_window(6.0, 1.2), sample_rate_hz=MYO_RATE_HZ).samples
        image = envelope_image.render(envelope, sample_rate_hz=MYO_RATE_HZ)

        assert math.isclose(image.metadata["duration_s"], len(envelope) / MYO_RATE_HZ)

    def test_an_empty_window_is_refused(self) -> None:
        with pytest.raises(ValueError, match="nothing to draw"):
            envelope_image.render([], sample_rate_hz=MYO_RATE_HZ)


class TestImageContextBlock:
    def test_it_states_the_band_that_was_actually_applied(self) -> None:
        """The block describes the stimulus, so it may not describe a filter
        that did not run. At 200 Hz the band is 20-95 Hz, and telling the model
        it is 20-450 Hz would be a plain falsehood in the one block whose entire
        job is accuracy about the picture."""
        from app.prompts.image_context import build_image_context

        text = build_image_context(bandpass_high_hz=95.0)

        assert "20-95 Hz" in text
        assert "450" not in text

    def test_it_describes_the_encoding_without_interpreting_it(self) -> None:
        """Interpretation lives in the EMG knowledge block, which the text flow
        shares. Two copies would drift, and the drift would be invisible."""
        from app.prompts.image_context import build_image_context

        text = build_image_context().lower()

        assert "shared" in text and "amplitude" in text
        assert "flexor" in text and "extensor" in text
        # No verdicts: naming a group's dominance as meaning a command would be
        # this block answering the question it is supposed to be posing.
        assert "closing" not in text
        assert "opening" not in text
