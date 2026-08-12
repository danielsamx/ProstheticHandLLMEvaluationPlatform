"""Prompt assembly: the experimental control surface.

Rewritten for the envelope-image flow. The previous file was the specification
of the text flow — a selectable dynamic block, a row cap, a stored template that
had to be prevented from defeating the mode switch — and roughly two thirds of
it described machinery that no longer exists. Those tests were not failing
because the assembly regressed; they were failing because they described a
different experiment.

What is pinned here is what would invalidate a run of *this* experiment: the
frozen material drifting between runs, the picture and the numbers describing
different signals, a sample matrix reappearing in the text beside the image, or
the answer key reaching the model.
"""

from __future__ import annotations

import inspect

from app.domain.hand_spec import EMG_CHANNEL_COUNT, Handedness, LimitProfileId, get_limit_profile
from app.prompts.builder import build_prompt
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.services.analysis_service import FeatureSource
from app.services.emg_service import synthesise_window


# ── The four blocks ─────────────────────────────────────────────────────────


def test_prompt_has_four_frozen_blocks_and_a_generated_user_turn():
    window = synthesise_window("power_grasp", seed=1)
    prompt = build_prompt(window)

    assert prompt.system_prompt
    assert prompt.emg_context
    assert prompt.image_context
    assert prompt.technical_context
    assert prompt.dynamic_prompt

    # Located in the joined text rather than counted by separator: the separator
    # is a blank line, which occurs inside blocks too, so counting it would
    # measure paragraph breaks instead of boundaries.
    text = prompt.full_prompt
    assert all(
        block in text
        for block in (prompt.system_prompt, prompt.emg_context,
                      prompt.image_context, prompt.technical_context,
                      prompt.dynamic_prompt)
    )


def test_the_frozen_blocks_reach_the_model_in_order():
    """System, how to read EMG, how to read the picture, then what the hand can
    do — and the stimulus last.

    The two EMG blocks sit together because they answer one question between
    them: what am I looking at. The hardware contract comes last, closest to the
    answer it constrains.
    """
    prompt = build_prompt(synthesise_window("rest", seed=1, samples=8))
    text = prompt.full_prompt

    assert (
        text.index(prompt.system_prompt)
        < text.index(prompt.emg_context)
        < text.index(prompt.image_context)
        < text.index(prompt.technical_context)
        < text.index(prompt.dynamic_prompt)
    )


def test_frozen_context_is_identical_across_different_emg_windows():
    """The whole design rests on this: only the stimulus may vary."""
    a = build_prompt(synthesise_window("power_grasp", seed=1))
    b = build_prompt(synthesise_window("hand_open", seed=2))
    assert a.frozen_context_sha256 == b.frozen_context_sha256
    assert a.dynamic_prompt_sha256 != b.dynamic_prompt_sha256


def test_the_limit_profile_no_longer_reaches_the_model():
    """It used to change the frozen context, because the actuator table quoted
    its bounds. The reduced contract has no actuator table, so the two profiles
    now produce byte-identical prompts.

    This is a real loss of information and is pinned rather than hidden: the
    profile still governs what the validator accepts, and is still recorded on
    the execution, so a run can be attributed to it. It simply no longer changes
    what the model was told — which is correct, because the model no longer
    names positions.
    """
    a = build_prompt(
        synthesise_window("rest", seed=1),
        limit_profile=get_limit_profile(LimitProfileId.TABLE_5_V3),
    )
    b = build_prompt(
        synthesise_window("rest", seed=1),
        limit_profile=get_limit_profile(LimitProfileId.ANNEX_A_V3),
    )
    assert a.frozen_context_sha256 == b.frozen_context_sha256
    assert a.limit_profile != b.limit_profile


def test_identical_inputs_produce_identical_hashes():
    """Including the picture. matplotlib stamps a creation date into PNG
    metadata by default, which would make the digest differ between two renders
    of the same window and prove nothing at all."""
    window = synthesise_window("precision_pinch", seed=99)
    first, second = build_prompt(window), build_prompt(window)

    assert first.full_prompt_sha256 == second.full_prompt_sha256
    assert first.image_sha256 == second.image_sha256


# ── The user turn ───────────────────────────────────────────────────────────


def test_the_user_turn_is_a_feature_table_and_a_picture():
    window = synthesise_window("power_grasp", seed=3, samples=404)
    prompt = build_prompt(window)

    block = prompt.dynamic_prompt
    assert block.startswith("DERIVED FEATURES")
    assert sum(line.startswith("CH") for line in block.splitlines()) == EMG_CHANNEL_COUNT
    assert "flexor_ratio" in block

    parts = prompt.messages[-1]["content"]
    assert [part["type"] for part in parts] == ["text", "image_url"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_no_sample_matrix_survives_anywhere_in_the_text():
    """The picture *is* the stimulus.

    Printing the matrix beside it sent about 10,000 tokens describing, badly and
    in text, the same window the model was being shown — and handed it two
    representations processed differently, with no way to know which to believe.
    """
    prompt = build_prompt(synthesise_window("rest", seed=3, samples=404))
    lines = prompt.full_prompt.splitlines()
    assert not any(line.startswith("[") and line.endswith("]") for line in lines)


def test_the_descriptors_omit_what_smoothing_destroys():
    """ZC and SSC are identically zero on the envelope — measured, on every
    channel. Printing a column of zeros invites the model to conclude there is
    no activity, which is a correct inference from a table that should never
    have contained the column."""
    block = build_prompt(synthesise_window("power_grasp", seed=3)).dynamic_prompt
    header = block.splitlines()[1]
    assert "ZC" not in header
    assert "SSC" not in header
    assert "RMS" in header and "MAV" in header and "WL" in header


def test_the_hand_never_appears_in_the_prompt():
    """A consequence worth pinning: the response schema still asks for `hand`,
    so the model must guess it. The pipeline records a mismatch against the
    configured hand as a warning rather than a failure."""
    right = build_prompt(synthesise_window("rest", seed=3), handedness=Handedness.RIGHT)
    left = build_prompt(synthesise_window("rest", seed=3), handedness=Handedness.LEFT)

    assert right.dynamic_prompt == left.dynamic_prompt
    assert right.full_prompt_sha256 == left.full_prompt_sha256


# ── The preprocessing toggle ────────────────────────────────────────────────


def test_the_toggle_governs_the_picture_and_the_table_together():
    """One switch, both halves of the stimulus.

    Two switches would allow the combination where the model is shown an
    envelope and told the numbers of the raw signal — a disagreement it has no
    way to detect and every reason to reason from.
    """
    window = synthesise_window("power_grasp", seed=5, samples=256)
    processed = build_prompt(window, feature_source=FeatureSource.PREPROCESSED)
    raw = build_prompt(window, feature_source=FeatureSource.RAW)

    assert processed.image_sha256 != raw.image_sha256
    assert processed.dynamic_prompt != raw.dynamic_prompt
    assert processed.image_context_sha256 != raw.image_context_sha256

    # And the image block stops claiming a filter chain that did not run.
    assert "rectification" in processed.image_context.lower()
    assert "rectification" not in raw.image_context.lower()


def test_the_image_block_states_the_band_that_actually_ran():
    """At 200 Hz — the Myo's rate — Nyquist is 100 Hz and the requested
    20-450 Hz band does not exist. The block has to say 20-95 Hz, because it is
    the one block whose entire job is describing the stimulus accurately."""
    window = synthesise_window("power_grasp", seed=5, samples=256, sample_rate_hz=200)
    prompt = build_prompt(window)

    assert "20-95 Hz" in prompt.image_context
    assert prompt.metadata["preprocessing"]["applied_bandpass_hz"][1] < 100


def test_the_feature_source_is_recorded_on_the_prompt():
    """Two runs over the same window under different toggles are different
    experiments, and the record has to say which one happened."""
    window = synthesise_window("rest", seed=3, samples=32)
    assert build_prompt(window).metadata["feature_source"] == "preprocessed"
    assert build_prompt(
        window, feature_source=FeatureSource.RAW
    ).metadata["feature_source"] == "raw"


def test_the_image_digest_is_recorded_because_the_stimulus_is_not_text():
    """Without it a stored execution cannot prove what the model was shown: the
    prompt text no longer contains the signal in any form."""
    prompt = build_prompt(synthesise_window("rest", seed=3, samples=32))
    assert prompt.image_sha256
    assert prompt.metadata["image_sha256"] == prompt.image_sha256
    assert prompt.metadata["image_width_px"] > 0


# ── Message roles ───────────────────────────────────────────────────────────


def test_the_frozen_material_stays_in_the_system_turn():
    """All four frozen blocks in the system message, the stimulus in the user
    turn. That is the boundary the whole design rests on."""
    prompt = build_prompt(synthesise_window("rest", seed=3, samples=8))

    assert len(prompt.messages) == 2
    assert prompt.messages[0]["content"] == prompt.frozen_context
    assert prompt.messages[1]["content"][0]["text"] == prompt.dynamic_prompt


def test_context_can_move_to_the_user_turn_for_awkward_runtimes():
    """Some LM Studio presets handle a long system message poorly. The picture
    travels with the text either way."""
    prompt = build_prompt(synthesise_window("rest", seed=3), merge_context_into_system=False)

    assert prompt.messages[0]["content"] == SYSTEM_PROMPT
    leading = prompt.messages[1]["content"][0]["text"]
    assert prompt.technical_context in leading
    assert prompt.image_context in leading
    assert any(part.get("type") == "image_url" for part in prompt.messages[1]["content"])


# ── Attribution ─────────────────────────────────────────────────────────────


def test_the_emg_block_enters_the_comparability_hash():
    """Changing what the model is told to conclude from a signal makes two runs
    incomparable, so the hash that claims comparability has to notice."""
    window = synthesise_window("rest", seed=1, samples=16)

    baseline = build_prompt(window)
    altered = build_prompt(window, emg_context="Different guidance entirely.")

    assert baseline.frozen_context_sha256 != altered.frozen_context_sha256
    assert baseline.dynamic_prompt_sha256 == altered.dynamic_prompt_sha256


def test_each_editable_block_can_be_varied_without_disturbing_the_others():
    """The reason for separate artefacts: an effect can only be attributed to a
    block if the others stayed byte-identical."""
    window = synthesise_window("rest", seed=1, samples=16)
    baseline = build_prompt(window)

    only_emg = build_prompt(window, emg_context="Read channel one only.")
    assert only_emg.system_prompt_sha256 == baseline.system_prompt_sha256
    assert only_emg.technical_context_sha256 == baseline.technical_context_sha256
    assert only_emg.emg_context_sha256 != baseline.emg_context_sha256

    only_hardware = build_prompt(window, technical_context="O opens. C closes.")
    assert only_hardware.emg_context_sha256 == baseline.emg_context_sha256
    assert only_hardware.technical_context_sha256 != baseline.technical_context_sha256


# ── The removed switches stay removed ───────────────────────────────────────


def test_the_builder_offers_no_way_to_send_the_matrix_again():
    """One flow, no branches. Every one of these parameters was a second path
    through the same function, and each carried its own way for the picture and
    the numbers to disagree.
    """
    parameters = inspect.signature(build_prompt).parameters
    for removed in ("dynamic_content", "dynamic_template", "matrix_max_rows",
                    "analysis_mode", "mechanical_telemetry", "mvc_by_channel"):
        assert removed not in parameters


def test_a_reviewers_note_is_the_only_text_that_can_be_added_to_the_user_turn():
    """The corrective-retry path re-runs a window with an account of what the
    hand actually did. The stimulus is regenerated identically, so the note is
    the only difference between the pair — which is what makes them comparable.
    """
    window = synthesise_window("rest", seed=7, samples=32)
    plain = build_prompt(window)
    corrected = build_prompt(window, feedback_note="GESTURE EXECUTION FEEDBACK:\n{}")

    assert corrected.dynamic_prompt.startswith(plain.dynamic_prompt)
    assert corrected.dynamic_prompt.endswith("GESTURE EXECUTION FEEDBACK:\n{}")
    assert corrected.image_sha256 == plain.image_sha256
    assert corrected.frozen_context_sha256 == plain.frozen_context_sha256
