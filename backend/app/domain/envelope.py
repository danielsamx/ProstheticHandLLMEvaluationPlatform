"""The linear envelope of a surface EMG window.

Band-pass, rectify, low-pass — the standard surface-electromyography chain, and
the one a reader will recognise without having to be persuaded of it. Each step
removes something specific:

* **Band-pass 20-450 Hz.** Below 20 Hz is movement artefact and baseline drift;
  above 450 Hz there is no muscle signal left, only noise. The band is where the
  motor unit action potentials actually live.
* **Rectify.** Surface EMG is bipolar and roughly zero-mean, so its average
  carries no information about effort. Taking the absolute value is what makes
  amplitude mean something.
* **Low-pass 4-10 Hz.** What survives is the *outline* of the burst rather than
  its oscillation, which is the quantity that corresponds to intent.

Every filter is zero-phase (:func:`scipy.signal.filtfilt`). A causal filter
shifts the signal in time, and the shift depends on frequency — which would move
the envelope relative to the movement that produced it. Since the entire premise
of the image flow is that a model reads the *shape over time*, a phase shift
would distort the very thing being measured.

Three limits are enforced rather than assumed, because all three fail silently:

**The sampling rate decides the usable band.** A Myo Armband samples at 200 Hz,
so its Nyquist frequency is 100 Hz and a 450 Hz cutoff cannot exist. Asking for
one is not a small error: :func:`~scipy.signal.butter` would raise, or worse,
a normalised frequency above 1 produces an unstable filter that returns
plausible-looking rubbish. The high cutoff is therefore clamped to just under
Nyquist and the clamp is **recorded in the metadata**, so a window filtered at
20-95 Hz is never mistaken for one filtered at 20-450 Hz.

**Mains hum lands inside the band and the band-pass cannot remove it.** This is
the consequence of the clamp that is easy to miss. At 1000 Hz the useful band
runs to 450 Hz and 60 Hz interference is one narrow component among many; at
200 Hz the band is 20-95 Hz, and 60 Hz sits almost exactly in the middle of it.
Measured on a gated broadband burst, skipping the notch left the resting
envelope at 0.97 against 1.37 during contraction — a ratio of 1.4, where most of
the "resting" amplitude was hum. The notch runs first, and its default is 60 Hz
because that is the Ecuadorian mains frequency.

**Short windows cannot be filtered at all.** ``filtfilt`` pads the signal by
three times the filter length; below that it raises. A window too short to
filter is returned rectified but unfiltered, and says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np
from scipy.signal import butter, filtfilt, iirnotch

from app.domain.hand_spec import EMG_CHANNEL_COUNT

#: The muscle band. Below 20 Hz is artefact, above 450 Hz is noise.
BANDPASS_LOW_HZ: Final[float] = 20.0
BANDPASS_HIGH_HZ: Final[float] = 450.0

#: Mains frequency, notched out before anything else.
#:
#: 60 Hz because the Escuela Politécnica Nacional is in Ecuador, whose grid runs
#: at 60 Hz. Anywhere on a 50 Hz grid this must be changed, and the value is
#: carried through to the stored metadata so a recording made under the wrong
#: setting can be identified rather than merely suspected.
MAINS_NOTCH_HZ: Final[float] = 60.0

#: Quality factor of the notch. High enough to take out the interference
#: without removing the muscle signal on either side of it.
NOTCH_Q: Final[float] = 30.0

#: The envelope cutoff, inside the conventional 4-10 Hz window.
#:
#: 6 Hz is a deliberate middle. Towards 4 Hz the envelope is smoother and a
#: brief burst can be flattened out of existence; towards 10 Hz the oscillation
#: starts to show through and the outline stops being an outline. Neither
#: failure is visible in the resulting image, which is why the value is a named
#: constant rather than a call-site default.
ENVELOPE_CUTOFF_HZ: Final[float] = 6.0

#: Fourth order, applied forwards and backwards, so the effective response is
#: eighth order with zero phase.
FILTER_ORDER: Final[int] = 4

#: How close to Nyquist a cutoff may sit. At exactly Nyquist the normalised
#: frequency is 1.0 and the design is degenerate.
_NYQUIST_MARGIN: Final[float] = 0.95

#: ``filtfilt`` pads by ``3 * max(len(a), len(b))``. For a fourth-order band-pass
#: the coefficient arrays hold nine values, so anything at or below 27 samples
#: cannot be filtered. The margin is not generosity: a window barely above the
#: limit is dominated by its own padding.
_MIN_SAMPLES_TO_FILTER: Final[int] = 64


@dataclass(frozen=True, slots=True)
class EnvelopeResult:
    """The envelope, and an honest account of how it was produced.

    ``metadata`` exists because the parameters that were *requested* and the
    ones that were *applied* can differ, and the difference changes what the
    signal means. A record that stored only the request would describe a filter
    that never ran.
    """

    samples: list[list[float]]
    metadata: dict = field(default_factory=dict)

    @property
    def was_filtered(self) -> bool:
        """False when the window was too short and only rectification ran."""
        return bool(self.metadata.get("bandpass_applied"))


def usable_band(sample_rate_hz: float) -> tuple[float, float, bool]:
    """The band that can actually be realised at this sampling rate.

    Returns ``(low, high, clamped)``. The third value is the one that matters:
    it is the difference between "filtered 20-450 Hz" and "filtered 20-95 Hz
    because the hardware samples at 200 Hz", and those are different signals.

    A Myo Armband streams at 200 Hz. Every textbook figure for surface EMG
    assumes 1000 Hz or more, so the canonical band is simply unavailable on this
    hardware — and code that silently substitutes a narrower one produces a
    result that looks canonical and is not.
    """
    nyquist = sample_rate_hz / 2.0
    ceiling = nyquist * _NYQUIST_MARGIN

    high = min(BANDPASS_HIGH_HZ, ceiling)
    low = BANDPASS_LOW_HZ

    if low >= high:
        # A sampling rate so low that the muscle band does not fit at all.
        # Reported rather than repaired: there is no honest filter to run.
        return (low, high, True)

    return (low, high, high < BANDPASS_HIGH_HZ)


def linear_envelope(
    samples: list[list[float]],
    *,
    sample_rate_hz: int,
    envelope_cutoff_hz: float = ENVELOPE_CUTOFF_HZ,
    mains_notch_hz: float | None = MAINS_NOTCH_HZ,
) -> EnvelopeResult:
    """Notch, band-pass, rectify, low-pass an N x 8 window.

    Parameters
    ----------
    samples
        The raw window, N rows by 8 columns, in converter units. Nothing is
        rescaled: the envelope is in the same units as the input, so two windows
        recorded at the same gain stay comparable.
    sample_rate_hz
        The acquisition rate. This is not bookkeeping — it decides the usable
        band, and getting it wrong silently changes which frequencies survive.
    envelope_cutoff_hz
        The low-pass corner, expected inside 4-10 Hz.
    mains_notch_hz
        Mains frequency to remove first, or ``None`` to skip. At 200 Hz sampling
        this step is doing most of the work: the band-pass cannot reject 60 Hz
        because 60 Hz is inside the only band the rate can represent.

    Raises
    ------
    ValueError
        If the matrix is not N x 8, or the cutoff is outside the band the
        sampling rate can represent.
    """
    data = np.asarray(samples, dtype=float)
    if data.ndim != 2 or data.shape[1] != EMG_CHANNEL_COUNT:
        raise ValueError(
            f"The window must be N x {EMG_CHANNEL_COUNT}; got {data.shape}."
        )
    if data.shape[0] == 0:
        raise ValueError("The window is empty.")

    nyquist = sample_rate_hz / 2.0
    if not 0 < envelope_cutoff_hz < nyquist:
        raise ValueError(
            f"An envelope cutoff of {envelope_cutoff_hz} Hz cannot be represented "
            f"at {sample_rate_hz} Hz (Nyquist is {nyquist} Hz)."
        )

    low, high, clamped = usable_band(sample_rate_hz)
    long_enough = data.shape[0] > _MIN_SAMPLES_TO_FILTER
    band_exists = low < high

    # The notch goes first, while the interference is still a single clean
    # component. After rectification it has been folded into the magnitude and
    # no linear filter can separate it out again.
    notch_applied = bool(mains_notch_hz) and long_enough and 0 < mains_notch_hz < nyquist
    if notch_applied:
        b, a = iirnotch(mains_notch_hz / nyquist, NOTCH_Q)
        data = filtfilt(b, a, data, axis=0)

    bandpass_applied = long_enough and band_exists
    if bandpass_applied:
        b, a = butter(FILTER_ORDER, [low / nyquist, high / nyquist], btype="band")
        data = filtfilt(b, a, data, axis=0)

    # Rectification is the step that makes amplitude meaningful, and it is the
    # one step that always runs: it needs no filter, no length and no band.
    data = np.abs(data)

    envelope_applied = long_enough
    if envelope_applied:
        b, a = butter(FILTER_ORDER, envelope_cutoff_hz / nyquist, btype="low")
        data = filtfilt(b, a, data, axis=0)
        # Zero-phase low-pass filtering can undershoot below zero at a sharp
        # edge. A negative envelope is not a small numerical wart: it is a
        # negative magnitude, which is meaningless, and it would set the floor
        # of every plot below zero.
        data = np.clip(data, 0.0, None)

    metadata = {
        "pipeline": "notch-bandpass-rectify-lowpass",
        "sample_rate_hz": sample_rate_hz,
        "mains_notch_hz": mains_notch_hz if notch_applied else None,
        "notch_applied": notch_applied,
        "requested_bandpass_hz": [BANDPASS_LOW_HZ, BANDPASS_HIGH_HZ],
        "applied_bandpass_hz": [low, high] if bandpass_applied else None,
        "bandpass_clamped_to_nyquist": clamped,
        "bandpass_applied": bandpass_applied,
        "rectified": True,
        "envelope_cutoff_hz": envelope_cutoff_hz if envelope_applied else None,
        "envelope_applied": envelope_applied,
        "filter_order": FILTER_ORDER,
        "zero_phase": True,
        "rows": int(data.shape[0]),
        "duration_s": round(data.shape[0] / sample_rate_hz, 4),
        "notes": _notes(
            long_enough, band_exists, clamped, sample_rate_hz, high, notch_applied, mains_notch_hz
        ),
    }

    return EnvelopeResult(samples=data.tolist(), metadata=metadata)


def _notes(
    long_enough: bool,
    band_exists: bool,
    clamped: bool,
    sample_rate_hz: float,
    high: float,
    notch_applied: bool,
    mains_notch_hz: float | None,
) -> list[str]:
    """Plain sentences for anything that did not go the textbook way.

    These reach the interface and the stored record. A caller should not have to
    compare two float lists to discover that the filter they think they applied
    did not run.
    """
    notes: list[str] = []

    if not long_enough:
        notes.append(
            f"Window shorter than {_MIN_SAMPLES_TO_FILTER} samples: rectified only, "
            "not filtered. The result is a rectified signal, not an envelope."
        )
    if not band_exists:
        notes.append(
            f"At {sample_rate_hz} Hz the muscle band above {BANDPASS_LOW_HZ} Hz does not "
            "fit below Nyquist. No band-pass was applied."
        )
    elif clamped:
        notes.append(
            f"Band-pass clamped to {BANDPASS_LOW_HZ:.0f}-{high:.0f} Hz: at {sample_rate_hz} Hz "
            f"the canonical {BANDPASS_HIGH_HZ:.0f} Hz upper cutoff is above Nyquist. "
            "This is expected on a Myo Armband and is not an error, but it is a "
            "different filter from the one the literature describes."
        )

    if mains_notch_hz and not notch_applied and long_enough:
        notes.append(
            f"A {mains_notch_hz:.0f} Hz notch was requested but cannot be represented at "
            f"{sample_rate_hz} Hz. Mains interference remains in the envelope."
        )
    elif notch_applied and clamped:
        notes.append(
            f"The {mains_notch_hz:.0f} Hz notch is load-bearing at this sampling rate: mains "
            f"interference falls inside the {BANDPASS_LOW_HZ:.0f}-{high:.0f} Hz band, so the "
            "band-pass alone would not have removed it."
        )

    return notes
