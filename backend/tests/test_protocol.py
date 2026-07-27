"""Serial codec: the wire format documented in the manual."""

from __future__ import annotations

import pytest

from app.domain.hand_spec import Actuator, ControlCommand
from app.domain.protocol import (
    ProtocolError,
    encode_positions,
    parse_serial_command,
)


def test_single_position_command():
    frame = parse_serial_command("A320")
    assert frame.positions == {Actuator.A_PINKY: 320}
    assert frame.controls == ()


def test_multiple_positions_in_one_line():
    frame = parse_serial_command("A320,B180,C400,D200")
    assert frame.positions == {
        Actuator.A_PINKY: 320,
        Actuator.B_RING: 180,
        Actuator.C_MIDDLE: 400,
        Actuator.D_INDEX: 200,
    }


def test_bare_c_closes_the_hand():
    """The documented ambiguity: 'C' alone is CLOSE, 'C400' is the middle finger."""
    frame = parse_serial_command("C")
    assert frame.controls == (ControlCommand.CLOSE,)
    assert frame.positions == {}


def test_c_with_position_is_the_middle_finger():
    frame = parse_serial_command("C400")
    assert frame.positions == {Actuator.C_MIDDLE: 400}
    assert frame.controls == ()


def test_emergency_stop_is_recognised():
    assert parse_serial_command("S").is_emergency_stop


@pytest.mark.parametrize("line", ["Z100", "a320", "A320;B180", "", "   ", "A", "A32.5"])
def test_malformed_frames_are_rejected(line):
    with pytest.raises(ProtocolError):
        parse_serial_command(line)


def test_gesture_cannot_be_mixed_with_positions():
    with pytest.raises(ProtocolError, match="cannot be combined"):
        parse_serial_command("P,A320")


def test_exclusive_commands_must_be_alone():
    with pytest.raises(ProtocolError, match="exclusive"):
        parse_serial_command("S,A320")


def test_duplicate_actuator_is_rejected():
    with pytest.raises(ProtocolError, match="more than once"):
        parse_serial_command("A320,A100")


def test_two_gestures_in_one_frame_is_rejected():
    with pytest.raises(ProtocolError):
        parse_serial_command("P,O")


def test_encode_uses_canonical_actuator_order():
    encoded = encode_positions({Actuator.F_THUMB_UPPER: 90, Actuator.A_PINKY: 10})
    assert encoded == "A10,F90"


def test_round_trip():
    line = "A320,B180,E120"
    assert parse_serial_command(line).encode() == line


def test_line_length_guard():
    with pytest.raises(ProtocolError, match="exceeds"):
        parse_serial_command(",".join(["A320"] * 40))
