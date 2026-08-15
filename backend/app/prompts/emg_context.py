"""Block 2 of 4 - how to read the descriptors.

The electrode map and the meaning of each figure in the feature table. Not the
picture — that is block 3 — and not the hand, which is block 4.

Rewritten for the envelope flow, and the rewrite is not cosmetic. The previous
text instructed the model to "evaluate jointly - raw EMG, RMS, MAV, WL, ZC,
SSC". Two of those are now unavailable and one is gone entirely:

* **Raw EMG never arrives.** The model sees an envelope, drawn.
* **ZC and SSC are identically zero** when the descriptors come from the
  preprocessed signal, measured: 0 and 0 on every channel, against 246 and 377
  on the same window unprocessed. Both count sign changes, and a rectified
  magnitude never crosses zero while a 6 Hz-smoothed curve barely changes slope.

Instructing a model to weigh evidence that is structurally absent is worse than
omitting it. A model told that zero crossings matter, and shown a column of
zeros, can reason correctly to "there is no activity" from a table that should
never have contained the column. The renderer omits those columns; this block
must not ask for them.

The channel map is generated from :mod:`app.domain`, so the anatomy the model is
told cannot drift from the grouping the feature extractor and the plot use.
"""

from __future__ import annotations

from typing import Final

from app.domain.hand_spec import EMG_CHANNEL_SITES

#: Every block starts at 1.0.
EMG_CONTEXT_VERSION: Final[str] = "1.0"
EMG_CONTEXT_NAME: Final[str] = "Myo Armband 8-channel EMG - envelope interpretation"


def _channel_table() -> str:
    """`CH1 Flexor digitorum superficialis`, one per line, from the domain."""
    return "\n".join(
        f"{channel} {site.split('(')[0].strip()}"
        for channel, site in EMG_CHANNEL_SITES.items()
    )


def build_emg_context() -> str:
    return f"""\
EMG KNOWLEDGE CONTEXT
Surface EMG is acquired from an eight-channel Myo Armband worn on the forearm.
Channels
{_channel_table()}
CH1 to CH4 are the volar flexor group. Contracting them closes the hand.
CH5 to CH8 are the dorsal extensor group. Contracting them opens the hand.
Descriptors
Every figure is computed over the complete window, not over an excerpt.
RMS and MAV measure how much muscle activity the channel carried.
WL measures how much the signal varied across the window.
MIN, MAX and VARIANCE describe the spread of that activity over time.
flexor_ratio is volar RMS divided by total RMS, and is the single most useful figure.
flexor_ratio near 1 means the flexor group dominates.
flexor_ratio near 0 means the extensor group dominates.
flexor_ratio near 0.5 means neither group dominates.
Only the descriptors present in the table carry evidence.
If a descriptor is absent it was removed because processing left it meaningless. Do not infer anything from its absence.
Deciding
Compare the two groups rather than reading any channel on its own.
Absolute amplitude depends on gain, electrode placement and the subject, so it does not transfer between recordings. The balance between groups does.
Normal movement activates both groups because antagonists stabilise the wrist. Simultaneous activity alone does not mean the hand should stay still.
Choose C to close when the flexor group clearly dominates and the image shows a sustained rise in the upper panels.
Choose O to open when the extensor group clearly dominates and the image shows a sustained rise in the lower panels.
Choose "" when both groups stay near their baseline, when neither clearly dominates, or when the image and the descriptors disagree.
Never substitute a movement for inaction.
"""


def default_emg_context() -> str:
    return build_emg_context()
