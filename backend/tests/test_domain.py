"""Domain invariants: the specification extracted from the manuals."""

from __future__ import annotations

import pytest

from app.domain.hand_spec import (
    ACTUATORS,
    DRIVEN_DOF,
    EMG_CHANNEL_COUNT,
    EXCLUSIVE_COMMANDS,
    FSR_COUNT,
    GESTURES,
    JOINTS,
    JOINTS_BY_ID,
    KINEMATIC_DOF,
    LIMIT_PROFILES,
    POTENTIOMETER_COUNT,
    Actuator,
    ControlCommand,
    Handedness,
    LimitProfileId,
    get_limit_profile,
)
from app.domain.kinematics import pose_from_gesture, pose_from_positions, rest_pose


def test_driven_dof_matches_manual():
    """Six commandable channels: A-F (Manual V3, Tabla 5)."""
    assert DRIVEN_DOF == 6
    assert len(ACTUATORS) == 6
    assert {a.value for a in Actuator} == set("ABCDEF")


def test_sensor_counts_match_wiring():
    """11 potentiometers (mux C5..C15) and 5 fingertip FSRs."""
    assert POTENTIOMETER_COUNT == 11
    assert FSR_COUNT == 5
    assert KINEMATIC_DOF == len(JOINTS) == 15


def test_every_joint_is_driven_by_a_real_actuator():
    for joint in JOINTS:
        assert joint.driven_by in ACTUATORS
        assert joint.id in ACTUATORS[joint.driven_by].joints


def test_actuator_joint_lists_are_consistent():
    for actuator, spec in ACTUATORS.items():
        for joint_id in spec.joints:
            assert JOINTS_BY_ID[joint_id].driven_by is actuator


@pytest.mark.parametrize("profile_id", list(LimitProfileId))
def test_limit_profiles_cover_every_actuator(profile_id):
    profile = LIMIT_PROFILES[profile_id]
    assert set(profile.limits) == set(Actuator)
    for actuator in Actuator:
        lo, hi = profile.bounds(actuator)
        assert 0 <= lo < hi


def test_table5_matches_the_manual_verbatim():
    profile = get_limit_profile(LimitProfileId.TABLE_5_V3)
    assert profile.bounds(Actuator.A_PINKY) == (0, 600)
    assert profile.bounds(Actuator.B_RING) == (0, 550)
    assert profile.bounds(Actuator.C_MIDDLE) == (0, 600)
    assert profile.bounds(Actuator.D_INDEX) == (0, 550)
    assert profile.bounds(Actuator.E_THUMB_LOWER) == (0, 130)
    assert profile.bounds(Actuator.F_THUMB_UPPER) == (0, 400)


def test_annex_a_is_the_conservative_reading():
    table5 = get_limit_profile(LimitProfileId.TABLE_5_V3)
    annex = get_limit_profile(LimitProfileId.ANNEX_A_V3)
    for actuator in Actuator:
        assert annex.bounds(actuator)[1] <= table5.bounds(actuator)[1]


def test_intersection_is_never_wider_than_either_source():
    inter = get_limit_profile(LimitProfileId.INTERSECTION)
    table5 = get_limit_profile(LimitProfileId.TABLE_5_V3)
    annex = get_limit_profile(LimitProfileId.ANNEX_A_V3)
    for actuator in Actuator:
        assert inter.bounds(actuator)[1] == min(
            table5.bounds(actuator)[1], annex.bounds(actuator)[1]
        )


def test_all_fourteen_gestures_are_present():
    """Manual V3, Tabla 6 + Anexo A: O C P R W Y L M H U G S X I."""
    assert len(GESTURES) == 14
    assert {c.value for c in GESTURES} == set("OCPRWYLMHUGSXI")


def test_system_commands_are_exclusive_and_poseless():
    for command in EXCLUSIVE_COMMANDS:
        assert GESTURES[command].pose is None
    assert ControlCommand.STOP in EXCLUSIVE_COMMANDS


def test_gesture_poses_are_normalised_and_complete():
    for command, gesture in GESTURES.items():
        if gesture.pose is None:
            continue
        assert set(gesture.pose) == set(Actuator), command
        assert all(0.0 <= v <= 1.0 for v in gesture.pose.values()), command


def test_emg_channel_count_is_eight():
    assert EMG_CHANNEL_COUNT == 8


# ── Kinematics ──────────────────────────────────────────────────────────────


def test_open_gesture_is_full_extension():
    pose = pose_from_gesture(ControlCommand.OPEN)
    assert all(v == 0.0 for v in pose.actuator_normalised.values())
    assert all(j.angle_deg == 0.0 for j in pose.joints)


def test_close_gesture_respects_every_joint_limit():
    pose = pose_from_gesture(ControlCommand.CLOSE)
    for state in pose.joints:
        joint = JOINTS_BY_ID[state.joint_id]
        assert joint.min_flexion_deg <= state.angle_deg <= joint.max_flexion_deg


def test_system_commands_have_no_renderable_pose():
    for command in (ControlCommand.STOP, ControlCommand.CALIBRATE, ControlCommand.INIT_SHIELDS):
        assert pose_from_gesture(command) is None


def test_positions_are_clamped_into_joint_space():
    profile = get_limit_profile()
    pose = pose_from_positions({Actuator.A_PINKY: 600}, profile=profile)
    pinky = [j for j in pose.joints if j.digit == "D5"]
    assert pose.actuator_normalised["A"] == 1.0
    # Coupling means the distal joint never reaches its own maximum at once.
    assert all(j.normalised <= 1.0 for j in pinky)


def test_unspecified_actuators_hold_their_previous_position():
    previous = {Actuator.C_MIDDLE: 300}
    pose = pose_from_positions({Actuator.A_PINKY: 100}, previous=previous)
    assert pose.actuator_positions["C"] == 300
    assert pose.actuator_positions["A"] == 100


def test_rest_pose_is_open_for_both_hands():
    for hand in Handedness:
        pose = rest_pose(hand)
        assert pose.handedness is hand
        assert all(v == 0.0 for v in pose.actuator_normalised.values())
