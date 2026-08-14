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
EMG_CONTEXT_VERSION: Final[str] = "2.0"
EMG_CONTEXT_NAME: Final[str] = "Semantic sEMG decision policy"


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
    return """\
SEMANTIC sEMG POLICY
The numerical signal has already been windowed, normalized, and serialized deterministically.
Do not request or reconstruct raw samples, RMS, MAV, ZC, SSC, or WL.
Use intent_candidate, confidence, stable_for_ms, activation levels, and trends as biological evidence.
Use detected_pattern_hint only when it is not unknown.
control_recommendation=no_action requires no_action and an empty serial command.
Co-contraction is represented as detected_pattern=co_contraction and does not mean hold.
Infer a supported gesture only when control_recommendation=infer_gesture and action_allowed=true.
Encoder evidence can veto biological intent but cannot invent a biological gesture.
"""


def default_emg_context() -> str:
    return build_emg_context()
