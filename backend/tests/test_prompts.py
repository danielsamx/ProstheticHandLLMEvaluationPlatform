"""Prompt assembly: the experimental control surface."""

from __future__ import annotations

from app.domain.hand_spec import Handedness, LimitProfileId, get_limit_profile
from app.prompts.builder import build_prompt
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.dynamic_prompt import DEFAULT_MATRIX_MAX_ROWS
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

    # Rows are present and well formed, capped by the print budget.
    matrix_rows = [ln for ln in block.splitlines() if ln.startswith("[") and ln.endswith("]")]
    assert matrix_rows
    assert len(matrix_rows) <= min(window.sample_count, DEFAULT_MATRIX_MAX_ROWS)
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
    assert len(matrix_rows) <= 64, "the printed excerpt must stay inside the row budget"
    assert "row is shown" in block
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


def test_system_prompt_demands_only_the_command():
    lowered = SYSTEM_PROMPT.lower()
    assert "one line containing only the serial command" in lowered
    assert "no json" in lowered
    assert "no explanation" in lowered


def test_technical_context_is_generated_not_copied():
    """It must contain the live limits, so it can never drift from the validators."""
    context = build_technical_context(get_limit_profile(LimitProfileId.TABLE_5_V3))
    assert "| A   | D5" in context
    assert "600" in context and "130" in context
    assert "WHAT TO SEND BACK" in context
    for letter in "OCPRWYLMHUGSXI":
        assert f"| {letter}   |" in context


def test_the_output_contract_is_one_line_not_a_document():
    """The response is the command itself, so the contract is four examples
    rather than a schema. Everything the old JSON carried besides the command
    was the model's account of its own reasoning, which the backend never
    trusted and now does not ask for."""
    context = build_technical_context()

    assert "ONE LINE containing ONLY the serial command" in context
    for example in ("  C", "  A320,B180,C400,D200", "  S"):
        assert example in context

    # No trace of the old document contract.
    assert '"$defs"' not in context
    assert "confidence" not in context
    assert "detected_pattern" not in context


def test_the_default_prompt_fits_a_small_local_context():
    """8k is LM Studio's usual default, and a 3B model is a realistic target.
    A prompt that cannot fit there is not a prompt this platform can use."""
    from app.prompts.budget import check

    window = synthesise_window("power_grasp", seed=1, samples=404)
    prompt = build_prompt(window)

    report = check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        context_window=8192,
    )
    assert report.fits, report.summary()


def test_technical_context_documents_the_c_ambiguity():
    context = build_technical_context()
    assert "DISAMBIGUATION" in context
    assert "bare `C`" in context
