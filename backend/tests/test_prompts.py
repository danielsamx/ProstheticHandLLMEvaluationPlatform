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


def test_the_dynamic_block_is_the_matrix_and_nothing_else():
    """Every line is a matrix row. No headings, no metadata, no feature table.

    The features are still computed and still stored on the window; they are
    simply no longer handed to the model. A feature table is a preprocessing
    step, and the question this platform asks is what an LLM does with raw EMG.
    """
    window = synthesise_window("rest", seed=3, samples=64)
    block = build_prompt(window).dynamic_prompt

    lines = block.splitlines()
    assert lines, "the block must not be empty"
    assert all(ln.startswith("[") and ln.endswith("]") for ln in lines)
    assert all(ln.count(",") == 7 for ln in lines)
    assert len(lines) <= min(window.sample_count, DEFAULT_MATRIX_MAX_ROWS)

    # The derived summary is gone from the prompt.
    for token in ("RMS", "flexor_ratio", "CH1", "Hand:", "Acquisition"):
        assert token not in block


def test_long_windows_are_decimated_without_announcing_it_in_the_prompt():
    """There is nowhere to put a note under a matrix-only contract, so the
    decimation factor is returned to the caller and recorded on the execution
    instead — where it stays queryable rather than buried in prompt text."""
    from app.prompts.dynamic_prompt import render_matrix_block

    window = synthesise_window("power_grasp", seed=3, samples=1000)
    block = build_prompt(window).dynamic_prompt
    lines = block.splitlines()

    assert len(lines) < window.sample_count
    assert len(lines) <= DEFAULT_MATRIX_MAX_ROWS

    _, rendered, factor = render_matrix_block(window)
    assert rendered == len(lines)
    assert factor > 1


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
    """The manual's one genuinely dangerous ambiguity: `C` alone closes the
    whole hand, `C400` drives the middle finger. A model that reads it the
    wrong way closes a fist when asked to extend one finger."""
    context = build_technical_context()
    assert "Bare C=CLOSE, C400=middle finger." in context
