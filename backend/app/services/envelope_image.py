"""The envelope, drawn as the image a vision model is asked to read.

Eight stacked traces on one shared time axis and **one shared amplitude scale**,
grouped flexors above extensors.

Every one of those choices is load-bearing:

**Stacked traces rather than a heat map.** A heat map is more compact, but it
asks the model to translate colour into magnitude before it can reason at all —
an extra inference step with nothing to anchor it. A line has a height, and
height is the quantity.

**One shared amplitude scale.** This is the decision most likely to be undone by
someone tidying the plot later, so it is worth stating plainly: if each channel
were scaled to its own maximum, a resting channel and a fully contracting one
would draw the same picture. The whole discriminative signal here is *relative*
amplitude between channels, and per-channel scaling destroys exactly that. It is
the same mistake as peak normalisation, committed in the renderer instead of the
parser.

**Flexors above extensors, in different colours.** Opening and closing are
distinguished by which group dominates. Grouping puts that comparison in one
saccade instead of asking the model to hold an electrode map in mind while
scanning eight interleaved rows.

**Deterministic bytes.** Two renders of one window must be byte-identical, or
the image digest stored with an execution is noise and cannot prove what the
model was shown. matplotlib stamps a creation date into PNG metadata by default,
which alone would make every render unique; it is suppressed.
"""

from __future__ import annotations

import base64
import hashlib
import io
from typing import Final

import matplotlib

# Selected before pyplot is imported. The container has no display, and the
# default interactive backend would fail at import time rather than at use.
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  (must follow the backend selection)

from app.domain.hand_spec import EMG_CHANNEL_COUNT  # noqa: E402

#: The project palette. Flexors pink, extensors navy - the same two colours the
#: interface uses, so the plot does not introduce a third visual language.
_FLEXOR_COLOUR: Final[str] = "#D81B60"
_EXTENSOR_COLOUR: Final[str] = "#001F3F"
_GRID_COLOUR: Final[str] = "#E2E8F0"

#: CH1-CH4 are volar, CH5-CH8 dorsal. Kept as a constant rather than derived
#: from a string search on the site names, which would break the moment someone
#: rewords the anatomy.
FLEXOR_CHANNELS: Final[tuple[int, ...]] = (0, 1, 2, 3)
EXTENSOR_CHANNELS: Final[tuple[int, ...]] = (4, 5, 6, 7)

#: Short labels. The full anatomy is in the EMG knowledge block; repeating it on
#: every trace would cost image area that the signal needs.
_CHANNEL_LABELS: Final[tuple[str, ...]] = (
    "CH1 FDS", "CH2 FCR", "CH3 FCU", "CH4 PL",
    "CH5 EDC", "CH6 ECRL", "CH7 ECU", "CH8 BR",
)

#: 1000 x 800 at 100 dpi. Large enough that a burst is unambiguous, small enough
#: that the vision encoder is not paying for empty white space.
FIGURE_WIDTH_IN: Final[float] = 10.0
FIGURE_HEIGHT_IN: Final[float] = 8.0
FIGURE_DPI: Final[int] = 100


class EnvelopeImage:
    """PNG bytes, plus the identity of those bytes.

    The digest is not decoration. It is what lets a stored execution prove which
    image a model actually saw, in a flow where the stimulus is no longer text
    that can simply be read back out of the record.
    """

    __slots__ = ("png", "sha256", "width", "height", "metadata")

    def __init__(self, png: bytes, width: int, height: int, metadata: dict):
        self.png = png
        self.sha256 = hashlib.sha256(png).hexdigest()
        self.width = width
        self.height = height
        self.metadata = metadata

    @property
    def data_url(self) -> str:
        """`data:image/png;base64,...`, the form both runtimes accept."""
        return "data:image/png;base64," + base64.b64encode(self.png).decode("ascii")

    @property
    def size_kb(self) -> float:
        return round(len(self.png) / 1024, 1)


def render(
    envelope: list[list[float]],
    *,
    sample_rate_hz: int,
    title: str | None = None,
) -> EnvelopeImage:
    """Draw an N x 8 envelope as one figure.

    Parameters
    ----------
    envelope
        The rectified, smoothed window from :func:`app.domain.envelope.linear_envelope`.
        Raw EMG can be passed and will draw, but the traces will be a solid band
        of oscillation rather than an outline, which is not what the image
        context block tells the model to expect.
    sample_rate_hz
        Used for the time axis. A wrong rate does not change the shape, only the
        numbers under it — but those numbers are what the model quotes back.

    Raises
    ------
    ValueError
        If the matrix is not N x 8 or is empty.
    """
    if not envelope:
        raise ValueError("The envelope is empty; there is nothing to draw.")
    if any(len(row) != EMG_CHANNEL_COUNT for row in envelope):
        raise ValueError(f"Every row must hold {EMG_CHANNEL_COUNT} channels.")

    rows = len(envelope)
    duration_s = rows / sample_rate_hz
    times = [index / sample_rate_hz for index in range(rows)]
    columns = [[row[channel] for row in envelope] for channel in range(EMG_CHANNEL_COUNT)]

    # One ceiling for all eight axes. Computed across every channel precisely so
    # that a quiet channel is drawn quiet.
    peak = max((max(column) for column in columns), default=0.0)
    ceiling = peak * 1.08 if peak > 0 else 1.0

    figure, axes = plt.subplots(
        EMG_CHANNEL_COUNT,
        1,
        figsize=(FIGURE_WIDTH_IN, FIGURE_HEIGHT_IN),
        dpi=FIGURE_DPI,
        sharex=True,
        sharey=True,
    )
    figure.patch.set_facecolor("white")

    for channel, axis in enumerate(axes):
        is_flexor = channel in FLEXOR_CHANNELS
        colour = _FLEXOR_COLOUR if is_flexor else _EXTENSOR_COLOUR

        axis.plot(times, columns[channel], color=colour, linewidth=1.4)
        axis.fill_between(times, columns[channel], color=colour, alpha=0.16)

        axis.set_ylim(0, ceiling)
        axis.set_xlim(0, duration_s)
        axis.set_yticks([0, ceiling])
        axis.grid(True, color=_GRID_COLOUR, linewidth=0.6)
        axis.set_axisbelow(True)

        # The label sits inside the axes, on the left. Outside, eight y-labels
        # would consume a fifth of the width for text the model reads once.
        axis.text(
            0.008, 0.72, _CHANNEL_LABELS[channel],
            transform=axis.transAxes, fontsize=9, fontweight="bold",
            color=colour, family="monospace",
        )

        for spine in ("top", "right"):
            axis.spines[spine].set_visible(False)
        axis.tick_params(labelsize=8, length=3)

        # Amplitude numbers only on the two group heads.
        #
        # Labelling all eight put each axis's ceiling directly against the next
        # axis's zero, which read as a column of colliding numbers and cost more
        # legibility than it bought. The scale is shared, so one labelled axis
        # per group states it once — and the title says so in words.
        #
        # Hidden with `tick_params`, never with empty `set_yticklabels`: these
        # axes are created with `sharey=True`, so they share one formatter and
        # blanking the labels on the last axis blanks them on all eight. That
        # exact mistake removed every amplitude number from the first render.
        axis.tick_params(labelleft=channel in (0, EXTENSOR_CHANNELS[0]))

        # The group heading rides inside its own axes, anchored to the top
        # right. Placed in figure coordinates it was clipped by the right margin
        # and collided with the boundary rule - and a caption that overlaps the
        # data is worse than no caption.
        if channel == 0:
            axis.text(0.995, 0.74, "FLEXORS · volar", transform=axis.transAxes,
                      ha="right", fontsize=9, fontweight="bold", color=_FLEXOR_COLOUR)
        elif channel == EXTENSOR_CHANNELS[0]:
            axis.text(0.995, 0.74, "EXTENSORS · dorsal", transform=axis.transAxes,
                      ha="right", fontsize=9, fontweight="bold", color=_EXTENSOR_COLOUR)

    # The group boundary, drawn between CH4 and CH5 in figure coordinates so it
    # reads as a division of the plot rather than as data on any one axis.
    boundary = (axes[3].get_position().y0 + axes[4].get_position().y1) / 2
    figure.add_artist(
        plt.Line2D(
            [0.045, 0.99], [boundary, boundary],
            color="#94A3B8", linewidth=1.0, linestyle=(0, (4, 3)),
        )
    )

    # Formatted once, after the loop, because the shared formatter is global to
    # all eight axes and the last write is the one that survives.
    axes[0].set_yticklabels(["0", f"{ceiling:.0f}" if ceiling >= 10 else f"{ceiling:.2f}"])

    axes[-1].set_xlabel("time (s)", fontsize=9)
    # The title names what is drawn, and must be told rather than assumed.
    #
    # Hard-coded as "linear envelope", it captioned a plot of raw samples with
    # the name of a process that had not been applied — a falsehood inside the
    # stimulus itself, in the one place a vision model is most likely to read
    # and believe.
    figure.suptitle(
        title or f"EMG · 8 channels · {duration_s:.2f} s · shared amplitude scale",
        fontsize=10, y=0.985,
    )
    figure.subplots_adjust(left=0.055, right=0.995, top=0.945, bottom=0.06, hspace=0.12)

    buffer = io.BytesIO()
    figure.savefig(
        buffer,
        format="png",
        facecolor="white",
        # Without this, matplotlib writes the current time into the PNG's
        # tEXt chunk and no two renders of the same window are ever equal.
        metadata={"Software": None, "Creation Time": None},
    )
    plt.close(figure)

    png = buffer.getvalue()
    return EnvelopeImage(
        png=png,
        width=int(FIGURE_WIDTH_IN * FIGURE_DPI),
        height=int(FIGURE_HEIGHT_IN * FIGURE_DPI),
        metadata={
            "layout": "8 stacked traces, shared time and amplitude axes",
            "grouping": "CH1-CH4 flexors (top), CH5-CH8 extensors (bottom)",
            "amplitude_ceiling": round(ceiling, 6),
            "shared_amplitude_scale": True,
            "duration_s": round(duration_s, 4),
            "rows": rows,
            "sample_rate_hz": sample_rate_hz,
            "width_px": int(FIGURE_WIDTH_IN * FIGURE_DPI),
            "height_px": int(FIGURE_HEIGHT_IN * FIGURE_DPI),
        },
    )
