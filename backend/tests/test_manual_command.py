"""Sending a command by hand, and logging what was sent.

The manual path exists to separate two failures that look identical from the
outside. When a run produces no movement, the cause is either the model's answer
or the plumbing — validator, WebSocket, serial link, firmware. Typing `C` and
watching the hand close settles that in one action.

It is not a shortcut around validation, and these tests are mostly about that:
the mechanical stops do not care who chose the number.
"""

from __future__ import annotations

import pytest

from app.domain.hand_spec import Handedness, LimitProfileId, get_limit_profile
from app.services.movement_service import ManualCommandError, validate_manual_command


# ── Accepted ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("typed,normalised", [
    ("C", "C"),
    ("c", "C"),
    ("  P  ", "P"),
    ("a320,b180", "A320,B180"),
    ("A320 , B180", "A320,B180"),
    ("S", "S"),
])
def test_a_valid_command_is_accepted_and_normalised(typed, normalised):
    """Typed loosely, sent exactly. A researcher testing the mechanics should not
    have to match the wire format by hand."""
    report = validate_manual_command(typed)
    assert report.passed
    assert report.normalised_serial == normalised


def test_an_accepted_command_resolves_a_pose_the_simulator_can_render():
    """Without a pose there is nothing to render, and the test would prove only
    that the request succeeded."""
    report = validate_manual_command("A320,B180")
    assert report.resolved_pose is not None
    assert report.resolved_pose.actuator_positions["A"] == 320


# ── Refused, by the same rules a model faces ────────────────────────────────


def test_a_position_past_a_mechanical_stop_is_refused():
    """The whole reason this goes through the pipeline. A typo in a text field
    can strip a gearmotor exactly as well as a bad model can."""
    with pytest.raises(ManualCommandError) as excinfo:
        validate_manual_command("E200")

    message = str(excinfo.value)
    assert "outside the documented range 0-130" in message
    assert "TABLE_5_V3" in message


def test_the_active_limit_profile_decides():
    """F380 is legal under Tabla 5 and illegal under the Anexo A envelope. The
    manual path must honour the same profile as a run, or a command that is safe
    to test would be unsafe to execute."""
    assert validate_manual_command(
        "F380", profile=get_limit_profile(LimitProfileId.TABLE_5_V3)
    ).passed

    with pytest.raises(ManualCommandError):
        validate_manual_command(
            "F380", profile=get_limit_profile(LimitProfileId.ANNEX_A_V3)
        )


@pytest.mark.parametrize("typed", ["Z100", "P,A320", "A320,A100", "S,A320", ""])
def test_malformed_and_contradictory_commands_are_refused(typed):
    with pytest.raises(ManualCommandError):
        validate_manual_command(typed)


def test_an_empty_field_says_what_to_type():
    """The most likely first interaction, and a bare "invalid" would leave the
    researcher guessing at the syntax."""
    with pytest.raises(ManualCommandError) as excinfo:
        validate_manual_command("   ")
    assert "for example C or A320,B180" in str(excinfo.value)


def test_the_manual_path_uses_the_pipeline_rather_than_a_second_validator():
    """Two definitions of "safe" would drift, and the guarantee would become
    whichever one happened to run. Asserted on the source because the property
    is structural: there must be exactly one validator."""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app" / "services" / "movement_service.py"
    ).read_text()
    assert "from app.validation.pipeline import validate_response" in source
    assert "report = validate_response(" in source


def test_handedness_reaches_the_resolved_pose():
    """A left-hand test on a right-hand configuration would render a mirrored
    grasp, which is the opposite of a useful check."""
    left = validate_manual_command("C", handedness=Handedness.LEFT)
    assert left.resolved_pose.handedness is Handedness.LEFT


def test_the_broadcast_payload_uses_the_pose_s_own_serialiser() -> None:
    """A second serialiser is a second thing to keep in step.

    The first version of `publish_pose` walked the joints with `state.__dict__`,
    which raised AttributeError — `JointState` is a slots dataclass and has no
    instance dictionary. But the shallow bug hid the real one: `HandPose.to_dict`
    already existed, already rounded the angles the way stored movements are
    rounded, and produced the shape the simulator was built to parse. A parallel
    walk over the fields could only ever agree with it or drift from it.
    """
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app" / "ws" / "emg_stream.py"
    ).read_text()
    assert "pose.to_dict()" in source

    # Only the *code* is checked, not the prose: the comment above the fix names
    # `__dict__` on purpose, to say why the obvious approach is impossible here.
    # A test that failed on its own explanation would be pressure to delete the
    # explanation.
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    assert "__dict__" not in code


def test_a_slots_dataclass_has_no_instance_dictionary() -> None:
    """Pinning the fact that made the original code impossible, so nobody
    reintroduces the pattern believing it works."""
    report = validate_manual_command("A320")
    joint = report.resolved_pose.joints[0]

    with pytest.raises(AttributeError):
        joint.__dict__  # noqa: B018


def test_the_pose_serialises_to_json_for_every_command_shape() -> None:
    """Gestures, positions and STOP take different paths through the kinematics
    — STOP resolves no pose at all — and the payload has to survive all three."""
    import json

    for command in ("C", "A320,B240", "P"):
        pose = validate_manual_command(command).resolved_pose
        payload = pose.to_dict()
        assert json.dumps(payload)
        assert len(payload["joints"]) == 15
        assert payload["duration_ms"] > 0

    # STOP is a halt, not a pose: nothing to render, and that must not raise.
    assert validate_manual_command("S").resolved_pose is None
