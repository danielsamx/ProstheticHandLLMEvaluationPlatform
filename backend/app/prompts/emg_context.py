"""Block 3 of 4 - the EMG Knowledge Context.

What the eight channels are, and how to reason about them. Frozen like blocks 1
and 2, and versioned separately from both.

Its own artefact because it answers a different kind of question. Block 2 says
what the hand can do — a fact about hardware that changes only when the hardware
does. This block says how EMG should be *interpreted*, which is a methodological
position a researcher will want to revise repeatedly: is co-contraction a stop
or is it physiological coactivation? Should a single channel crossing a
threshold ever decide anything? Those are hypotheses, and each revision is an
experiment.

Kept inside block 2, every such experiment would also reversion the hardware
description, and the two effects would be impossible to attribute apart. Split
out, a run can vary this block alone while blocks 1 and 2 stay byte-identical.

The interpretation guidance here is deliberately *against* the naive reading.
Earlier versions of this platform told the model that near-equal flexor and
extensor activity meant STOP. That is wrong physiologically: a normal grasp
recruits antagonists to stabilise the wrist, so a rule keyed on simultaneous
activity turns ordinary grasping into an emergency halt. The text now says so
explicitly, because a model given the simple rule will follow it.
"""

from __future__ import annotations

from typing import Final

from app.domain.hand_spec import EMG_CHANNEL_SITES

#: Every block starts at 1.0.
#:
#: The numbers used to carry the platform's own development history — a system
#: prompt at 6.0.0 before anyone had run an experiment, because it had been
#: rewritten six times while the code was being built. That history is in git,
#: where it belongs; here it only made the artefact table read as though five
#: earlier studies had happened.
#:
#: From here the version means what a researcher expects it to mean: 1.0 is the
#: text this platform ships with, and anything above it is a change someone
#: made deliberately and can be asked about.
EMG_CONTEXT_VERSION: Final[str] = "1.1"
EMG_CONTEXT_NAME: Final[str] = "Myo Armband 8-channel EMG - interpretation"


def _channel_table() -> str:
    """`CH1 Flexor Digitorum Superficialis`, one per line.

    Generated from the domain so the electrode map in the prompt is the same one
    the feature extractor groups by. If they diverged, the model would be told a
    channel is a flexor while the flexor ratio counted it as an extensor.
    """
    rows = []
    for channel, site in EMG_CHANNEL_SITES.items():
        muscle = site.split(" (")[0]
        rows.append(f"{channel} {muscle.title()}")
    return "\n".join(rows)


def build_emg_context() -> str:
    """Render the EMG knowledge block."""
    return f"""\
EMG KNOWLEDGE CONTEXT
Surface EMG is acquired from an eight-channel Myo Armband.
Channels
{_channel_table()}
Interpret the complete activation pattern.
Do not classify movements from a single threshold.
Evaluate jointly
- raw EMG
- RMS
- MAV
- WL
- ZC
- SSC
- spatial distribution
- relative activation
Normal grasping may activate both flexors and extensors because of physiological coactivation.
Simultaneous agonist and antagonist activity alone does not indicate STOP.
Infer the movement whose overall pattern is most consistent with the observed EMG.
If evidence is insufficient return no_action.
When intent is no_action, leave serial_command empty and send no gesture.
no_action means the hand does not move. It is never S, and never O.
Return STOP only when ALL of the following are true:
1. Flexor and extensor activation are both high.
2. Their activation is approximately balanced across most channels.
3. No grasp, pinch, point, thumbs-up, call-me, OK or other supported gesture better explains the pattern.
4. The overall EMG is more consistent with intentional simultaneous contraction than with any hand movement.
"""


def default_emg_context() -> str:
    return build_emg_context()
