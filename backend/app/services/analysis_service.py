"""The analysis flow, from a loaded window to the blocks a model sees.

One entry point, :func:`analyse`, because the steps are not independent and
letting a caller order them itself is how the envelope ends up drawn from
unfiltered data, or the features computed from a signal the image does not show.

The path — the only one — is:

    raw window
      -> notch, band-pass, rectify, low-pass        (app.domain.envelope)
      -> plot as eight stacked traces               (app.services.envelope_image)
      -> descriptors over the plotted signal        (app.services.emg_features)
      -> four blocks: system, EMG, image, technical

There used to be a second path that printed the raw matrix as text, selected by
an ``AnalysisMode`` enum. It is gone. It answered a different question — *can a
model read raw EMG?* — and keeping both meant every function downstream had to
say what it did in each, which is where an image drawn from one signal and a
feature table computed from another becomes possible. The question this platform
now asks is the one the flow implements: *can a vision model read a drawn
envelope and decide open or close?*

**Whether the signal is preprocessed at all remains a real variable.**
:class:`FeatureSource` is that switch, and it governs the picture and the table
together: descriptors taken from the raw signal and from the envelope are
different numbers describing the same window, and showing a model an envelope
plot beside raw descriptors would give it two views processed differently and no
way to know it. Both arms are defensible, neither is obviously right, and the
choice is recorded so a result can be attributed to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.domain.envelope import ENVELOPE_CUTOFF_HZ, MAINS_NOTCH_HZ, linear_envelope
from app.domain.hand_spec import EMG_CHANNELS
from app.services import emg_features, envelope_image
from app.services.envelope_image import (
    EXTENSOR_CHANNELS,
    FLEXOR_CHANNELS,
    EnvelopeImage,
)


class FeatureSource(str, Enum):
    """Which signal is drawn and measured — the preprocessing toggle itself.

    One switch for both halves of the stimulus. Splitting it into "draw the
    envelope" and "measure the envelope" would allow the combination where the
    model is shown one signal and told the numbers of another.
    """

    #: Straight from the converter. Zero crossings and slope sign changes mean
    #: what the literature says they mean.
    RAW = "raw"

    #: From the rectified, smoothed envelope. RMS and MAV become cleaner
    #: measures of effort; ZC and SSC lose almost all of their content, because
    #: a smoothed magnitude barely crosses zero and rarely changes slope.
    PREPROCESSED = "preprocessed"


#: The default, stated once so the interface, the API and the tests cannot
#: disagree about what "default" means.
DEFAULT_FEATURE_SOURCE = FeatureSource.PREPROCESSED


@dataclass(slots=True)
class AnalysisResult:
    """Everything derived from one window, and how it was derived."""

    feature_source: FeatureSource

    #: The cleaned signal. ``None`` when the toggle is off and nothing was
    #: cleaned — the picture then shows the raw window.
    envelope: list[list[float]] | None = None

    #: The picture, when one was drawn.
    image: EnvelopeImage | None = None

    #: Per-channel descriptors plus the aggregate ratios.
    features: dict[str, Any] = field(default_factory=dict)

    #: What the filter actually did, including any clamping it had to do.
    preprocessing: dict[str, Any] = field(default_factory=dict)

    @property
    def has_image(self) -> bool:
        return self.image is not None

    def provenance(self) -> dict[str, Any]:
        """The record's account of this analysis.

        Deliberately includes the image digest. In the image flow the stimulus
        is no longer text that can be read back out of the record, so without
        the digest a stored execution cannot prove what the model was shown.
        """
        return {
            "feature_source": self.feature_source.value,
            "image_sha256": self.image.sha256 if self.image else None,
            "image_width_px": self.image.width if self.image else None,
            "image_height_px": self.image.height if self.image else None,
            "image_size_kb": self.image.size_kb if self.image else None,
            "preprocessing": self.preprocessing,
        }


def analyse(
    samples: list[list[float]],
    *,
    sample_rate_hz: int,
    feature_source: FeatureSource | str = DEFAULT_FEATURE_SOURCE,
    envelope_cutoff_hz: float = ENVELOPE_CUTOFF_HZ,
    mains_notch_hz: float | None = MAINS_NOTCH_HZ,
    include_features: bool = True,
) -> AnalysisResult:
    """Run one window through the flow: preprocess, draw, measure.

    Raises
    ------
    ValueError
        Propagated from the envelope chain for a malformed or unfilterable
        window, and from the renderer for an empty one. Not swallowed: a caller
        that silently received an unprocessed window would send the model a
        picture of noise and record it as a result.
    """
    feature_source = FeatureSource(feature_source)
    preprocessed = feature_source is FeatureSource.PREPROCESSED

    envelope: list[list[float]] | None = None
    preprocessing: dict[str, Any] = {}

    # Computed once, for the picture and the table together. Filtering for the
    # image and filtering again for the descriptors would be two chances to
    # disagree — and it is only computed when the toggle is on, so a run with
    # preprocessing off cannot record filter metadata describing a chain that
    # never touched what the model saw.
    if preprocessed:
        result = linear_envelope(
            samples,
            sample_rate_hz=sample_rate_hz,
            envelope_cutoff_hz=envelope_cutoff_hz,
            mains_notch_hz=mains_notch_hz,
        )
        envelope = result.samples
        preprocessing = result.metadata

    # The signal the model is shown and the signal it is given numbers for are
    # by construction the same object.
    analysed = envelope if preprocessed else samples
    duration = len(analysed) / sample_rate_hz
    image = envelope_image.render(
        analysed,
        sample_rate_hz=sample_rate_hz,
        title=(
            f"EMG linear envelope · 8 channels · {duration:.2f} s · shared amplitude scale"
            if preprocessed
            else f"Raw EMG, unprocessed · 8 channels · {duration:.2f} s · shared amplitude scale"
        ),
    )

    features: dict[str, Any] = {}
    if include_features:
        channels = emg_features.extract_matrix_features(analysed, EMG_CHANNELS)
        features = {
            # Named on the result rather than left to the caller to remember. A
            # feature table with no note of its origin is the sort of thing that
            # gets pasted into a paper as though there were only one kind.
            "source": feature_source.value,
            "channels": channels,
            "flexor_ratio": _flexor_ratio(channels),
            "meaningless": _meaningless_descriptors(feature_source),
        }

    return AnalysisResult(
        feature_source=feature_source,
        envelope=envelope,
        image=image,
        features=features,
        preprocessing=preprocessing,
    )


#: Descriptors that carry no information once the signal has been rectified and
#: smoothed.
#:
#: Measured, not assumed: on a gated 200 Hz window the envelope yields exactly
#: ``zc=0`` and ``ssc=0`` on every channel, against 246 and 377 on the raw
#: signal. Both count sign changes, and a rectified magnitude never crosses zero
#: while a 6 Hz-smoothed curve barely changes slope. They are not merely
#: degraded — they are identically zero, on every window, forever.
#:
#: This matters beyond tidiness. The EMG knowledge block instructs the model to
#: "evaluate jointly - raw EMG, RMS, MAV, WL, ZC, SSC ...". Feeding it a table
#: where two of those are always zero asks it to weigh evidence that does not
#: exist, and a model that dutifully reports "no zero crossings, therefore no
#: activity" would be reasoning correctly from a table that lied to it.
_DESTROYED_BY_SMOOTHING: tuple[str, ...] = ("zc", "ssc")


def _meaningless_descriptors(source: FeatureSource) -> tuple[str, ...]:
    """Which descriptors must not be presented as evidence for this source."""
    return _DESTROYED_BY_SMOOTHING if source is FeatureSource.PREPROCESSED else ()


def _flexor_ratio(channels: list[dict[str, Any]]) -> float | None:
    """Volar RMS over total RMS - the quantity that survives everything.

    Gain, electrode placement and subject all move the absolute scale; the ratio
    between the two groups survives all three, which is why it is the number
    worth carrying beside the per-channel table rather than leaving the model to
    compute it from eight figures.

    ``None`` rather than 0.5 when both groups are silent. A resting window has
    no balance to report, and reporting perfect balance would look exactly like
    a co-contraction.
    """
    def group_rms(indices: tuple[int, ...]) -> float:
        return sum(float(channels[i].get("rms", 0.0)) for i in indices)

    flexor = group_rms(FLEXOR_CHANNELS)
    total = flexor + group_rms(EXTENSOR_CHANNELS)
    return round(flexor / total, 4) if total > 0 else None


def render_feature_block(features: dict[str, Any]) -> str:
    """The descriptor table, as the model reads it.

    Rendered from the analysis result rather than recomputed from the window.
    The predecessor did recompute — from the raw window, always — which made the
    preprocessing toggle a value in the record with no effect on the prompt: two
    runs labelled `raw` and `preprocessed` were handed identical text. A setting
    that appears in the provenance but not in the stimulus is worse than no
    setting at all.

    Descriptors known to be meaningless for the chosen source are **omitted**,
    not printed as zeros. Printing ``zc=0`` on all eight channels invites the
    model to conclude there is no activity, which is a correct inference from a
    table that should never have shown the column.
    """
    channels: list[dict[str, Any]] = features.get("channels", [])
    if not channels:
        return ""

    hidden = set(features.get("meaningless", ()))
    columns = [
        key for key in ("rms", "mav", "wl", "zc", "ssc", "min", "max", "variance")
        if key not in hidden
    ]

    source = features.get("source", "raw")
    header = " ".join(f"{key.upper():>10}" for key in columns)
    rows = [
        f"{channel.get('label', f'CH{index + 1}'):<5}"
        + " ".join(f"{float(channel.get(key, 0.0)):>10.4f}" for key in columns)
        for index, channel in enumerate(channels)
    ]

    ratio = features.get("flexor_ratio")
    tail = (
        f"flexor_ratio {ratio:.4f} (volar RMS / total RMS)"
        if ratio is not None
        else "flexor_ratio unavailable: both groups are silent"
    )
    note = (
        f"\n{', '.join(sorted(hidden)).upper()} are omitted: rectification and smoothing "
        "leave them identically zero, so they carry no evidence."
        if hidden
        else ""
    )

    return (
        f"DERIVED FEATURES (computed from the {source} signal)\n"
        f"{'':<5}{header}\n" + "\n".join(rows) + f"\n{tail}{note}\n"
    )


def applied_bandpass_high_hz(preprocessing: dict[str, Any]) -> float | None:
    """The upper cutoff that actually ran, for the image context block.

    Pulled out because the block must describe the filter that was applied, not
    the one that was requested: at 200 Hz the band is clamped to 20-95 Hz, and
    a block claiming 20-450 Hz would be a plain falsehood in the one place whose
    whole job is describing the stimulus accurately.
    """
    band = preprocessing.get("applied_bandpass_hz")
    return float(band[1]) if band else None
