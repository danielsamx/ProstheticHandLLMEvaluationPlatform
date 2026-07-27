"""Prompt assembly: the experimental control surface."""

from __future__ import annotations

from app.domain.hand_spec import Handedness, LimitProfileId, get_limit_profile
from app.prompts.builder import build_prompt
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.technical_context import build_technical_context
from app.services.emg_service import synthesise_window


def test_prompt_has_exactly_three_blocks():
    window = synthesise_window("power_grasp", seed=1)
    prompt = build_prompt(window)
    assert prompt.system_prompt
    assert prompt.technical_context
    assert prompt.dynamic_prompt
    assert prompt.full_prompt.count("=" * 78) == 2


def test_frozen_context_is_identical_across_different_emg_windows():
    """The whole design rests on this: only the dynamic block may vary."""
    a = build_prompt(synthesise_window("power_grasp", seed=1))
    b = build_prompt(synthesise_window("hand_open", seed=2))
    assert a.frozen_context_sha256 == b.frozen_context_sha256
    assert a.dynamic_prompt_sha256 != b.dynamic_prompt_sha256


def test_frozen_context_changes_when_the_limit_profile_changes():
    a = build_prompt(
        synthesise_window("rest", seed=1),
        limit_profile=get_limit_profile(LimitProfileId.TABLE_5_V3),
    )
    b = build_prompt(
        synthesise_window("rest", seed=1),
        limit_profile=get_limit_profile(LimitProfileId.ANNEX_A_V3),
    )
    assert a.frozen_context_sha256 != b.frozen_context_sha256


def test_identical_inputs_produce_identical_hashes():
    window = synthesise_window("precision_pinch", seed=99)
    assert (
        build_prompt(window).full_prompt_sha256
        == build_prompt(window).full_prompt_sha256
    )


def test_dynamic_block_carries_the_matrix_and_the_feature_table():
    window = synthesise_window("rest", seed=3, samples=64)
    block = build_prompt(window).dynamic_prompt

    # Layout is stated explicitly so the model cannot assume a transpose.
    assert "rows x 8 columns" in block
    assert "Column order = CH1, CH2, CH3, CH4, CH5, CH6, CH7, CH8" in block

    # Every sample row is present, each with eight signed values.
    matrix_rows = [ln for ln in block.splitlines() if ln.startswith("[") and ln.endswith("]")]
    assert len(matrix_rows) == window.sample_count
    assert all(row.count(",") == 7 for row in matrix_rows)

    # ...and the derived summary for all eight electrodes.
    for index in range(1, 9):
        assert f"| CH{index} |" in block


def test_long_windows_are_decimated_and_the_excerpt_is_labelled():
    """The feature table must still describe the full window, not the excerpt."""
    window = synthesise_window("power_grasp", seed=3, samples=1000)
    block = build_prompt(window).dynamic_prompt

    matrix_rows = [ln for ln in block.splitlines() if ln.startswith("[") and ln.endswith("]")]
    assert len(matrix_rows) < window.sample_count
    assert "every 4th row is shown" in block
    assert "computed from" in block


def test_hand_selection_reaches_the_dynamic_block_only():
    right = build_prompt(synthesise_window("rest", seed=3), handedness=Handedness.RIGHT)
    left = build_prompt(synthesise_window("rest", seed=3), handedness=Handedness.LEFT)
    assert "Hand: Right" in right.dynamic_prompt
    assert "Hand: Left" in left.dynamic_prompt
    assert right.frozen_context_sha256 == left.frozen_context_sha256


def test_message_roles_keep_the_frozen_material_in_the_system_turn():
    prompt = build_prompt(synthesise_window("rest", seed=3), merge_context_into_system=True)
    assert prompt.messages[0]["role"] == "system"
    assert prompt.messages[1]["role"] == "user"
    assert prompt.messages[1]["content"] == prompt.dynamic_prompt


def test_context_can_move_to_the_user_turn_for_awkward_runtimes():
    prompt = build_prompt(synthesise_window("rest", seed=3), merge_context_into_system=False)
    assert prompt.messages[0]["content"] == SYSTEM_PROMPT
    assert prompt.technical_context in prompt.messages[1]["content"]


def test_system_prompt_forbids_natural_language():
    lowered = SYSTEM_PROMPT.lower()
    assert "never write natural language" in lowered
    assert "single valid json object" in lowered


def test_technical_context_is_generated_not_copied():
    """It must contain the live limits, so it can never drift from the validators."""
    context = build_technical_context(get_limit_profile(LimitProfileId.TABLE_5_V3))
    assert "| A   | D5" in context
    assert "600" in context and "130" in context
    assert "OUTPUT JSON SCHEMA" in context
    for letter in "OCPRWYLMHUGSXI":
        assert f"| {letter}   |" in context


def test_technical_context_documents_the_c_ambiguity():
    context = build_technical_context()
    assert "DISAMBIGUATION" in context
    assert "bare `C`" in context
