"""Prompt assembly: the experimental control surface."""

from __future__ import annotations

from app.domain.hand_spec import Handedness, LimitProfileId, get_limit_profile
from app.prompts.builder import build_prompt
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.dynamic_prompt import DynamicContent
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


def test_the_matrix_mode_sends_every_row_of_the_window():
    """N rows x 8 columns, complete.

    The cap used to be 32 printed rows, so an imported 404-row recording
    reached the model as an eighth of itself while the interface reported the
    full count. Nothing warned about the difference, which made it capable of
    invalidating a conclusion without anyone noticing.
    """
    window = synthesise_window("rest", seed=3, samples=404)
    block = build_prompt(window, dynamic_content=DynamicContent.MATRIX).dynamic_prompt

    lines = block.splitlines()
    assert len(lines) == window.sample_count == 404
    assert all(ln.startswith("[") and ln.endswith("]") for ln in lines)
    assert all(ln.count(",") == 7 for ln in lines)

    # Matrix mode carries no descriptors and no metadata.
    for token in ("RMS", "flexor_ratio", "CH1", "Hand:", "Acquisition"):
        assert token not in block


def test_the_features_mode_sends_descriptors_and_no_matrix():
    window = synthesise_window("power_grasp", seed=3, samples=404)
    block = build_prompt(window, dynamic_content=DynamicContent.FEATURES).dynamic_prompt

    assert not any(ln.startswith("[") for ln in block.splitlines())
    for index in range(1, 9):
        assert f"| CH{index} |" in block
    assert "flexor_ratio" in block


def test_the_both_mode_carries_the_matrix_and_then_the_descriptors():
    window = synthesise_window("power_grasp", seed=3, samples=64)
    block = build_prompt(window, dynamic_content=DynamicContent.BOTH).dynamic_prompt

    matrix_rows = [ln for ln in block.splitlines() if ln.startswith("[")]
    assert len(matrix_rows) == window.sample_count
    assert "| CH1 |" in block
    assert block.index("[") < block.index("| CH1 |"), "matrix first, then the summary"


def test_the_three_modes_produce_three_different_prompts():
    """They are three different experiments, so they must not collide in the
    record: a shared hash would make them indistinguishable in the history."""
    window = synthesise_window("rest", seed=3, samples=32)
    hashes = {
        build_prompt(window, dynamic_content=mode).dynamic_prompt_sha256
        for mode in DynamicContent
    }
    assert len(hashes) == 3


def test_the_mode_and_the_row_count_are_recorded_on_the_prompt():
    """A run that saw 404 rows and one that saw 32 are not comparable, and the
    difference is invisible unless the record says which happened."""
    window = synthesise_window("rest", seed=3, samples=404)

    full = build_prompt(window, dynamic_content=DynamicContent.MATRIX)
    assert full.metadata["dynamic_content"] == "matrix"
    assert full.metadata["matrix_rows_sent"] == 404

    capped = build_prompt(window, matrix_max_rows=32)
    assert capped.metadata["matrix_rows_sent"] == 32
    assert len(capped.dynamic_prompt.splitlines()) == 32


def test_a_cap_still_decimates_rather_than_truncates():
    """A capped view must span the whole window. Printing the first 32 rows
    would show the model the pre-movement baseline and nothing else."""
    from app.prompts.dynamic_prompt import render_matrix_block

    window = synthesise_window("power_grasp", seed=3, samples=1000)
    _, rendered, factor = render_matrix_block(window, max_rows=32)
    assert rendered == 32
    assert factor > 1


def test_the_default_mode_is_the_raw_matrix():
    """The condition the platform exists to measure, and what a reader should
    assume when a run does not say otherwise."""
    window = synthesise_window("rest", seed=3, samples=16)
    assert (
        build_prompt(window).dynamic_prompt
        == build_prompt(window, dynamic_content=DynamicContent.MATRIX).dynamic_prompt
    )


def test_the_hand_no_longer_appears_anywhere_in_the_prompt():
    """A consequence worth pinning: the response schema still asks for `hand`,
    so the model must now guess it. The pipeline records a mismatch against the
    configured hand as a warning rather than a failure."""
    right = build_prompt(synthesise_window("rest", seed=3), handedness=Handedness.RIGHT)
    left = build_prompt(synthesise_window("rest", seed=3), handedness=Handedness.LEFT)

    assert right.dynamic_prompt == left.dynamic_prompt
    assert right.full_prompt_sha256 == left.full_prompt_sha256


def test_message_roles_keep_the_frozen_material_in_the_system_turn():
    prompt = build_prompt(synthesise_window("rest", seed=3), merge_context_into_system=True)
    assert prompt.messages[0]["role"] == "system"
    assert prompt.messages[1]["role"] == "user"
    assert prompt.messages[1]["content"] == prompt.dynamic_prompt


def test_context_can_move_to_the_user_turn_for_awkward_runtimes():
    prompt = build_prompt(synthesise_window("rest", seed=3), merge_context_into_system=False)
    assert prompt.messages[0]["content"] == SYSTEM_PROMPT
    assert prompt.technical_context in prompt.messages[1]["content"]


def test_system_prompt_demands_json_and_internal_agreement():
    lowered = SYSTEM_PROMPT.lower()
    assert "valid json only" in lowered
    assert "no prose, markdown or code fences" in lowered
    # The clause the `consistency` stage exists to enforce.
    assert "serial_command must match intent/gesture/commands" in lowered


def test_technical_context_is_generated_not_copied():
    """Every figure must come from the domain, so the text the model reads can
    never promise a range the validators then reject."""
    context = build_technical_context(get_limit_profile(LimitProfileId.TABLE_5_V3))
    assert "A(pinky 0-600)" in context
    assert "E(thumb_lower 0-130)" in context
    for letter in "OCPRWYLMHUGSXI":
        assert f"{letter}=" in context


def test_the_limit_profile_reaches_the_commands_line():
    """The two profiles disagree because the manual disagrees with itself. The
    prompt has to state whichever one the execution is actually validated
    against, or a correct answer under one would be scored against the other."""
    table5 = build_technical_context(get_limit_profile(LimitProfileId.TABLE_5_V3))
    annexa = build_technical_context(get_limit_profile(LimitProfileId.ANNEX_A_V3))
    assert "F(thumb_upper 0-400)" in table5
    assert "F(thumb_upper 0-100)" in annexa


def test_the_output_contract_states_every_field_the_schema_accepts():
    """The model is told the exact shape it will be validated against. A field
    checked but never stated would be an unfair failure; one stated but never
    checked would be dead text costing context on every run."""
    context = build_technical_context()

    assert "Valid JSON only. No prose." in context
    for field in ("hand", "intent", "gesture", "commands", "serial_command",
                  "confidence", "safety"):
        assert f'"{field}"' in context

    for letter in "OCPRWYLMHUGSXI":
        assert f'"{letter}"' in context


def test_a_full_recording_overflows_a_small_context_and_says_so_usefully():
    """The honest cost of sending the whole matrix, stated before the request.

    404 rows will not fit an 8k context. That is not a bug to be hidden by
    silently decimating — it is a fact the researcher has to decide about, so
    the budget names the two levers that exist: fewer rows, or a bigger
    context. The advice quotes a row count rather than a token count, because
    rows are the thing they can actually set.
    """
    from app.prompts.budget import check

    window = synthesise_window("power_grasp", seed=1, samples=404)
    prompt = build_prompt(window)

    report = check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        context_window=8192,
        matrix_rows=404,
    )
    assert not report.fits
    advice = " ".join(report.advice)
    assert "404 rows sent" in advice
    assert "rows alongside the frozen blocks" in advice
    assert "features only" in advice


def test_features_only_fits_a_small_context_comfortably():
    """The escape hatch the advice points at has to actually work: the
    descriptors are a fixed size whatever the recording length."""
    from app.prompts.budget import check

    window = synthesise_window("power_grasp", seed=1, samples=4000)
    prompt = build_prompt(window, dynamic_content=DynamicContent.FEATURES)

    report = check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        context_window=8192,
    )
    assert report.fits, report.summary()
    assert report.utilisation < 0.35


def test_a_capped_matrix_still_fits_a_small_context():
    """The other lever: 32 rows is what the prompt used to send, and it still
    fits, so a researcher on an 8k model is not locked out."""
    from app.prompts.budget import check

    window = synthesise_window("power_grasp", seed=1, samples=404)
    prompt = build_prompt(window, matrix_max_rows=32)

    report = check(
        system_prompt=prompt.system_prompt,
        technical_context=prompt.technical_context,
        dynamic_prompt=prompt.dynamic_prompt,
        context_window=8192,
    )
    assert report.fits, report.summary()


def test_technical_context_documents_the_c_ambiguity():
    """The manual's one genuinely dangerous ambiguity: `C` alone closes the
    whole hand, `C400` drives the middle finger. A model that reads it the
    wrong way closes a fist when asked to extend one finger."""
    context = build_technical_context()
    assert "Bare C=CLOSE, C400=middle finger." in context
