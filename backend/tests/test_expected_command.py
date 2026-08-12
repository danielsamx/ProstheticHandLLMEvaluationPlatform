"""The answer key: what a window should produce, and whether the model did.

Passing validation only says the command was well formed, in range and safe.
Whether it was the *right* command is a separate question, and one the platform
could not previously answer at all — a model that returns a perfectly valid `O`
for every window scores 100% on validation and 0% on control.
"""

from __future__ import annotations

import json

import pytest

from app.domain.hand_spec import Handedness
from app.domain.protocol import normalise_expected_command
from app.services.metrics_service import compute_metrics
from app.services.emg_service import synthesise_window
from app.validation.pipeline import validate_response


def response(serial: str, **extra) -> str:
    tokens = [t.strip() for t in serial.split(",") if t.strip()]
    positions = [t for t in tokens if len(t) > 1]
    is_gesture = bool(tokens) and not positions
    payload = {
        "hand": "right",
        "intent": "stop" if serial == "S" else "gesture" if is_gesture else "joint_positions",
        "gesture": tokens[0] if is_gesture else None,
        "commands": [
            {"actuator": t[0], "position": int(t[1:]), "speed_pct": 60} for t in positions
        ],
        "serial_command": serial,
        "confidence": 0.8,
        "safety": {"within_limits": True},
    }
    payload.update(extra)
    return json.dumps(payload)


def metrics_for(serial: str, expected: str | None):
    report = validate_response(response(serial), expected_hand=Handedness.RIGHT)
    return compute_metrics(
        report=report,
        call=None,
        window=synthesise_window("power_grasp", seed=1, samples=16),
        handedness=Handedness.RIGHT,
        profile=None,
        expected_serial_command=expected,
    )


# ── Normalisation ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("typed,stored", [
    ("c", "C"),
    ("  C  ", "C"),
    ("a320, b180", "A320,B180"),
    ("A320 , B180", "A320,B180"),
    ("", None),
    (None, None),
])
def test_a_hand_typed_expectation_is_tidied_not_interpreted(typed, stored):
    """A researcher should not have to match the wire format exactly to get a
    correct comparison — `a320, b180` and `A320,B180` are the same intent."""
    assert normalise_expected_command(typed) == stored


def test_a_malformed_expectation_is_accepted_as_written():
    """Deliberately not validated. An expected command that turns out to be
    wrong is the researcher's own to see in the dashboard; rejecting it at entry
    would block them from recording a run while they work out the right answer.
    """
    assert normalise_expected_command("Z999") == "Z999"


# ── Comparison ──────────────────────────────────────────────────────────────


def test_a_matching_command_is_recorded_as_a_match():
    assert metrics_for("C", "C")["command_matches_expected"] is True


def test_a_differing_command_is_recorded_as_a_miss():
    assert metrics_for("O", "C")["command_matches_expected"] is False


def test_an_unlabelled_run_is_neither():
    """NULL, not False. "Not compared" and "compared and wrong" must not share a
    value: averaging them together would let unlabelled runs drag the accuracy
    figure down without ever appearing in its denominator."""
    assert metrics_for("C", None)["command_matches_expected"] is None


def test_the_comparison_uses_the_normalised_frame_not_the_raw_string():
    """`A320, B180` and `A320,B180` drive the hand identically. Scoring them as
    different answers would measure formatting rather than control."""
    report = validate_response(
        response("A320, B180"), expected_hand=Handedness.RIGHT
    )
    assert report.passed
    assert report.normalised_serial == "A320,B180"

    result = compute_metrics(
        report=report, call=None,
        window=synthesise_window("rest", seed=1, samples=16),
        handedness=Handedness.RIGHT, profile=None,
        expected_serial_command="A320,B180",
    )
    assert result["command_matches_expected"] is True


def test_a_valid_but_wrong_command_still_fails_the_comparison():
    """The whole point. `O` passes every validation stage — it is well formed,
    in range, safe and executable — and is still the wrong answer for a window
    that should have closed the hand."""
    result = metrics_for("O", "C")
    assert result["protocol_compliant"] is True
    assert result["safety_compliant"] is True
    assert result["command_matches_expected"] is False


def test_the_expected_command_never_reaches_the_prompt():
    """It is the answer key. A prompt that contained it would make every
    measurement taken with it worthless."""
    from app.prompts.builder import build_prompt

    window = synthesise_window("power_grasp", seed=1, samples=16)
    prompt = build_prompt(window)

    # The builder has no parameter for it, so nothing in the assembled prompt
    # can carry it. This asserts the design rather than a value.
    #
    # It used to assert the word "expected" was absent from the prompt, which
    # was a proxy for the wrong thing: the system prompt legitimately says that
    # no_action is "a valid and expected answer", and a test that forbids the
    # English word forbids the block from explaining itself. What must not
    # appear is the answer key, and the only route for it is the signature.
    import inspect
    assert "expected_serial_command" not in inspect.signature(build_prompt).parameters
    assert "expected_serial_command" not in prompt.metadata
