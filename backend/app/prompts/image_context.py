"""Block 3 of the image flow - what the picture is.

A vision model handed a plot with no explanation has to infer the encoding
before it can read the data: which axis is time, whether the traces share a
scale, what the colours mean, whether a flat line is a quiet muscle or a dead
electrode. Every one of those inferences is a place to go wrong silently, and a
wrong one produces a confident answer about a chart that does not exist.

This block removes the guessing. It states the encoding, and only the encoding.

What it deliberately does **not** contain:

* **No interpretation rules.** "Flexors dominant means closing" belongs to the
  EMG knowledge block, which is shared with the text flow. Saying it twice would
  create two copies to keep in agreement, and the copies would drift.
* **No pixel dimensions or colour hex codes.** The model reads the picture, not
  its file format, and specifics that the renderer might change would become
  quiet lies the moment someone adjusts the figure size.
* **No claim about what the answer should be.** Describing the stimulus is not
  the same as suggesting the response, and a block that drifts into the second
  is a block that leaks the answer key.

Generated from the renderer's own constants, so the description cannot come
adrift from the drawing. If someone regroups the channels in
:mod:`app.services.envelope_image`, this text changes with them.
"""

from __future__ import annotations

from typing import Final

from app.domain.envelope import (
    BANDPASS_LOW_HZ,
    ENVELOPE_CUTOFF_HZ,
    MAINS_NOTCH_HZ,
)
from app.services.envelope_image import EXTENSOR_CHANNELS, FLEXOR_CHANNELS

#: Every block starts at 1.0.
IMAGE_CONTEXT_VERSION: Final[str] = "1.0"
IMAGE_CONTEXT_NAME: Final[str] = "EMG envelope plot - how to read the image"


def _channel_range(indices: tuple[int, ...]) -> str:
    """`CH1-CH4`, from the renderer's own grouping."""
    return f"CH{indices[0] + 1}-CH{indices[-1] + 1}"


def build_image_context(
    *,
    preprocessed: bool = True,
    bandpass_high_hz: float | None = None,
    mains_notch_hz: float | None = MAINS_NOTCH_HZ,
) -> str:
    """Describe the plot the model is about to be shown.

    ``bandpass_high_hz`` is passed in rather than taken from the constant
    because it is clamped by the sampling rate: at 200 Hz the band is 20-95 Hz,
    not 20-450 Hz. Telling the model it is looking at a 450 Hz band when it is
    not would be a plain falsehood in the one block whose entire job is to
    describe the stimulus accurately.

    ``preprocessed`` follows the same rule and is not cosmetic. With the toggle
    off the picture is the unfiltered window: a block that still recited the
    filter chain would describe a signal that was never drawn, and would also
    tell the model the trace cannot be negative when the raw plot swings either
    side of zero.
    """
    high = f"{bandpass_high_hz:.0f}" if bandpass_high_hz else "the Nyquist limit"
    notch = (
        f"A {mains_notch_hz:.0f} Hz notch removed mains interference.\n"
        if mains_notch_hz
        else ""
    )

    opening = (
        f"""\
The image is a plot of one processed EMG window. It is the only stimulus.
Processing applied before plotting
Band-pass {BANDPASS_LOW_HZ:.0f}-{high} Hz.
{notch}Full-wave rectification.
Low-pass {ENVELOPE_CUTOFF_HZ:.0f} Hz to obtain the linear envelope.
All filters are zero-phase, so no feature is shifted in time."""
        if preprocessed
        else """\
The image is a plot of one raw EMG window. It is the only stimulus.
Processing applied before plotting
None. The samples are drawn exactly as they were acquired.
The trace oscillates around zero and takes both signs; its amplitude is the
width of that oscillation, not its height above the axis."""
    )
    axis_label = "envelope amplitude" if preprocessed else "signal amplitude"
    sign_note = (
        "The envelope is a magnitude: it is never negative."
        if preprocessed
        else "The raw signal is bipolar: it crosses zero constantly, and that is not activity."
    )

    return f"""\
IMAGE CONTEXT
{opening}
Layout
Eight stacked panels, one per channel, in order {_channel_range(FLEXOR_CHANNELS)} then \
{_channel_range(EXTENSOR_CHANNELS)} from top to bottom.
The horizontal axis is time in seconds, identical in every panel.
The vertical axis is {axis_label}, and every panel uses the SAME scale.
Because the amplitude scale is shared, panel heights are directly comparable.
A low trace is a quiet muscle, not a rescaled one.
Grouping
{_channel_range(FLEXOR_CHANNELS)} are the volar flexor group, drawn in the upper block.
{_channel_range(EXTENSOR_CHANNELS)} are the dorsal extensor group, drawn in the lower block.
A dashed line separates the two groups.
Reading
Amplitude is the height of a trace above its own baseline.
Compare groups by their heights on the shared scale.
{sign_note}
A flat trace near zero means that channel was inactive during the window.
"""


def default_image_context() -> str:
    return build_image_context()
