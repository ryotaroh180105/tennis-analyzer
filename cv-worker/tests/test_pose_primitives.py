"""指標計算プリミティブの純粋関数テスト（12-form-analysis.md §指標エンジン）。"""

import pytest

from cvpipeline.pose.primitives import (
    angle_delta,
    event_interval,
    forward_of_body,
    joint_angle,
    line_separation,
    line_separation_signed,
    relative_height,
    resolve_role,
)


def _neutral_joints():
    return {
        "left_shoulder": {"x": -0.2, "y": -0.5, "z": 0.0, "visibility": 0.9},
        "right_shoulder": {"x": 0.2, "y": -0.5, "z": 0.0, "visibility": 0.9},
        "left_elbow": {"x": -0.25, "y": -0.2, "z": 0.0, "visibility": 0.9},
        "right_elbow": {"x": 0.25, "y": -0.2, "z": 0.0, "visibility": 0.9},
        "left_wrist": {"x": -0.25, "y": 0.1, "z": 0.0, "visibility": 0.9},
        "right_wrist": {"x": 0.25, "y": 0.1, "z": 0.0, "visibility": 0.9},
        "left_hip": {"x": -0.1, "y": 0.0, "z": 0.0, "visibility": 0.9},
        "right_hip": {"x": 0.1, "y": 0.0, "z": 0.0, "visibility": 0.9},
        "left_knee": {"x": -0.1, "y": 0.5, "z": 0.0, "visibility": 0.9},
        "right_knee": {"x": 0.1, "y": 0.5, "z": 0.0, "visibility": 0.9},
        "left_ankle": {"x": -0.1, "y": 1.0, "z": 0.0, "visibility": 0.9},
        "right_ankle": {"x": 0.1, "y": 1.0, "z": 0.0, "visibility": 0.9},
    }


def test_resolve_role_dominant_and_nondominant():
    joints = _neutral_joints()
    assert resolve_role("dominant_wrist", "right", joints) is joints["right_wrist"]
    assert resolve_role("nondominant_wrist", "right", joints) is joints["left_wrist"]
    assert resolve_role("dominant_knee", "left", joints) is joints["left_knee"]


def test_resolve_role_rejects_unknown_role():
    with pytest.raises(ValueError):
        resolve_role("dominant_head", "right", _neutral_joints())
    with pytest.raises(ValueError):
        resolve_role("racket_tip", "right", _neutral_joints())


def test_joint_angle_straight_leg_is_180():
    joints = _neutral_joints()  # hip-knee-ankleが一直線
    value = joint_angle(joints, "right", {"points": ["dominant_hip", "dominant_knee", "dominant_ankle"]})
    assert value == pytest.approx(180.0, abs=0.5)


def test_joint_angle_bent_knee_is_less_than_straight():
    joints = _neutral_joints()
    joints["right_knee"]["x"] = 0.3
    value = joint_angle(joints, "right", {"points": ["dominant_hip", "dominant_knee", "dominant_ankle"]})
    assert value < 170


def test_joint_angle_missing_role_returns_none():
    joints = _neutral_joints()
    del joints["right_wrist"]
    value = joint_angle(joints, "right", {"points": ["dominant_shoulder", "dominant_elbow", "dominant_wrist"]})
    assert value is None


def test_relative_height_uses_torso_scale():
    joints = _neutral_joints()
    value = relative_height(joints, "right", {"point": "dominant_elbow", "ref": "dominant_shoulder"})
    # |elbow.y - shoulder.y| / dist(shoulder, hip)
    expected = abs(-0.2 - -0.5) / ((0.2 - 0.1) ** 2 + (-0.5 - 0.0) ** 2) ** 0.5
    assert value == pytest.approx(round(expected, 3), abs=0.01)


def test_forward_of_body_positive_when_wrist_ahead_of_hips():
    joints = _neutral_joints()
    joints["right_wrist"]["z"] = -0.3  # カメラに近い側＝前方（primitives.pyの規約）
    value = forward_of_body(joints, "right", {"point": "dominant_wrist"})
    assert value > 0


def test_line_separation_zero_when_shoulders_and_hips_aligned():
    joints = _neutral_joints()  # 肩・腰とも z=0 で平行
    value = line_separation(joints, "right", {"lines": ["shoulder_line", "hip_line"]})
    assert value == pytest.approx(0.0, abs=0.5)


def test_line_separation_detects_rotation_difference():
    joints = _neutral_joints()
    joints["right_shoulder"]["z"] = 0.3  # 肩だけ捻る
    value = line_separation(joints, "right", {"lines": ["shoulder_line", "hip_line"]})
    assert value > 10


def test_line_separation_signed_sign_flips_with_rotation_direction():
    joints_a = _neutral_joints()
    joints_a["right_shoulder"]["z"] = 0.3  # 肩がhipより前方(z-)寄りに回旋 → 片手打ち想定
    positive = line_separation_signed(joints_a, "right", {"lines": ["shoulder_line", "hip_line"]})

    joints_b = _neutral_joints()
    joints_b["left_shoulder"]["z"] = 0.3  # 逆向きの回旋 → 両手打ち想定
    negative = line_separation_signed(joints_b, "right", {"lines": ["shoulder_line", "hip_line"]})

    assert positive > 0
    assert negative < 0
    # abs()を取らない点だけがline_separationとの違い
    assert line_separation_signed(joints_a, "right", {"lines": ["shoulder_line", "hip_line"]}) == pytest.approx(
        line_separation(joints_a, "right", {"lines": ["shoulder_line", "hip_line"]})
    )


def test_event_interval_computes_ms_between_events():
    frames_by_event = {"a": {"t": 0.3}, "b": {"t": 0.7}}
    assert event_interval(frames_by_event, {"from_event": "a", "to_event": "b"}) == 400.0


def test_event_interval_missing_event_returns_none():
    frames_by_event = {"a": {"t": 0.3}}
    assert event_interval(frames_by_event, {"from_event": "a", "to_event": "b"}) is None


def test_angle_delta_between_two_frames():
    straight = {"t": 0.0, "joints": _neutral_joints()}
    bent_joints = _neutral_joints()
    bent_joints["right_elbow"]["y"] = -0.35
    bent = {"t": 0.2, "joints": bent_joints}
    frames_by_event = {"start": straight, "end": bent}
    value = angle_delta(
        frames_by_event,
        "right",
        {"points": ["dominant_shoulder", "dominant_elbow", "dominant_wrist"], "from_event": "start", "to_event": "end"},
    )
    assert value > 0
