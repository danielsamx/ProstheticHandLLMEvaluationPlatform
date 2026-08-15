"""Contract tests for the four frozen blocks.

Rewritten for the envelope-image flow. The previous version pinned the semantic
redesign — `execute_handi_command`, `control_recommendation`,
`detected_pattern=co_contraction` — which was the vocabulary of a serialised
multimodal state that no longer exists. Those assertions did not fail because
the blocks regressed; they failed because they described a different platform.

What is pinned here is what would actually invalidate a run: the model being
told to weigh evidence it is not given, or being handed two contradictory
contracts about what it may answer.
"""

from app.prompts.emg_context import EMG_CONTEXT_VERSION, build_emg_context
from app.prompts.image_context import IMAGE_CONTEXT_VERSION, build_image_context
from app.prompts.system_prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION
from app.prompts.technical_context import (
    TECHNICAL_CONTEXT_OPEN_CLOSE_VERSION,
    build_technical_context,
    build_technical_context_open_close,
)


def test_every_block_starts_at_one_point_zero():
    assert SYSTEM_PROMPT_VERSION == "1.0"
    assert EMG_CONTEXT_VERSION == "1.0"
    assert IMAGE_CONTEXT_VERSION == "1.0"
    assert TECHNICAL_CONTEXT_OPEN_CLOSE_VERSION == "1.0"


def test_system_prompt_states_the_stimulus_and_the_three_answers():
    assert "one image of a processed surface EMG window" in SYSTEM_PROMPT
    assert "exactly one field, gesture" in SYSTEM_PROMPT
    assert 'permitted values of gesture are "O" to open, "C" to close, and ""' in SYSTEM_PROMPT
    # Inaction has to be named as an acceptable outcome. Left unsaid it reads as
    # a failure state, and a model avoiding it turns an ambiguous window into a
    # guess — which moves a motor.
    assert '{"gesture": ""} is a valid and expected answer' in SYSTEM_PROMPT
    # And the fields that are gone must not be asked for anywhere: a prompt that
    # names a field the schema forbids sets the model up to violate the schema.
    for removed in ("intent", "serial_command", "confidence", "no_action"):
        assert removed not in SYSTEM_PROMPT


def test_the_emg_block_does_not_ask_for_descriptors_the_flow_destroys():
    """ZC and SSC are identically zero on a rectified, smoothed signal.

    Measured: 0 and 0 on every channel against 246 and 377 on the same window
    raw. A block that told the model to weigh them, beside a table that omits
    them, asks it to reason about evidence that cannot exist.
    """
    text = build_emg_context()
    assert "flexor_ratio" in text
    for absent in ("ZC", "SSC", "zero crossing", "slope sign"):
        assert absent not in text


def test_the_emg_block_names_the_three_permitted_outcomes():
    text = build_emg_context()
    assert "Choose C to close" in text
    assert "Choose O to open" in text
    assert 'Choose ""' in text


def test_the_image_block_describes_the_filter_that_actually_ran():
    """At 200 Hz the band is clamped to 20-95 Hz. The block must say so."""
    clamped = build_image_context(bandpass_high_hz=95.0)
    assert "20-95 Hz" in clamped
    assert "450" not in clamped


def test_the_image_block_stops_claiming_filtering_when_there_was_none():
    """The preprocessing toggle governs this block too.

    With it off the picture is the unfiltered window, and a block still reciting
    the filter chain would describe a signal that was never drawn — while also
    telling the model the trace cannot be negative, which of a raw EMG plot is
    simply false.
    """
    raw = build_image_context(preprocessed=False)
    assert "None. The samples are drawn exactly as they were acquired." in raw
    assert "rectification" not in raw.lower()
    assert "never negative" not in raw
    assert "bipolar" in raw


def test_the_technical_block_offers_only_open_and_close():
    """The reduced vocabulary is only meaningful if the other one is gone.

    Leaving the fourteen-gesture table in place and adding "but only answer O or
    C" would give the model two contracts and let it choose.
    """
    text = build_technical_context_open_close()
    assert "These three are the only permitted answers." in text
    assert "Actuators" not in text
    for gesture in ("PINCH", "THREE", "CALIBRATION"):
        assert gesture not in text


def test_no_block_leaks_platform_or_transport_internals():
    """The model does not open the socket, and cannot act on anything here."""
    frozen = (
        SYSTEM_PROMPT
        + build_technical_context_open_close()
        + build_emg_context()
        + build_image_context()
    )
    for leak in ("Bluetooth", "PostgreSQL", "WebSocket", "frozen_context", "matplotlib"):
        assert leak not in frozen


def test_the_full_contract_still_renders_for_the_records_that_used_it():
    """`build_technical_context` is no longer sent, and is not yet deleted.

    Executions recorded under the fourteen-gesture contract are still in the
    database, and the artefact they point at has to keep rendering for the
    record to be readable. Pinned here so its removal is a decision rather than
    a collateral edit.
    """
    text = build_technical_context()
    assert "Actuators" in text
    assert "Physical encoders take priority over simulated encoders" in text
