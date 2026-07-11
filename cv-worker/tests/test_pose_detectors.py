"""ショット別フェーズ検出器の純粋関数テスト（12-form-analysis.md §ショット別フェーズモデル）。"""

from cvpipeline.pose.detectors import detect_groundstroke, detect_serve_like, detect_volley, dominant_side


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


def _frame(t, **wrist_overrides):
    joints = _neutral_joints()
    for key, val in wrist_overrides.items():
        joints[key].update(val)
    return {"t": round(t, 2), "joints": joints, "visible_ratio": 0.9}


def test_dominant_side_picks_larger_wrist_range():
    series = [
        _frame(0.0),
        _frame(0.1, right_wrist={"y": -1.0}),
        _frame(0.2, right_wrist={"y": 0.1}, left_wrist={"y": -0.2}),
    ]
    assert dominant_side(series) == "right"


def test_detect_serve_like_returns_none_with_too_few_frames():
    assert detect_serve_like([_frame(0.0), _frame(0.1)], "right") is None


def test_detect_serve_like_finds_toss_trophy_impact():
    window = [
        _frame(0.0, left_wrist={"y": 0.1}, right_wrist={"y": 0.1}),
        _frame(0.1, left_wrist={"y": -0.2}, right_wrist={"y": 0.1}),
        _frame(0.2, left_wrist={"y": -0.6}, right_wrist={"y": 0.1}),  # トス頂点
        _frame(0.3, left_wrist={"y": -0.4}, right_wrist={"y": -0.3}, left_knee={"x": 0.3}),  # トロフィー（軸足＝非利き手側の膝を曲げる）
        _frame(0.4, left_wrist={"y": -0.2}, right_wrist={"y": -1.2}),  # インパクト
        _frame(0.5, left_wrist={"y": 0.0}, right_wrist={"y": -0.6}),
    ]
    result = detect_serve_like(window, "right")
    assert result is not None
    assert result["toss_apex"]["t"] == 0.2
    assert result["trophy"]["t"] == 0.3
    assert result["impact"]["t"] == 0.4


def test_detect_groundstroke_returns_none_with_too_few_frames():
    assert detect_groundstroke([_frame(0.0)], "right") is None


def test_detect_groundstroke_finds_backswing_contact_follow():
    window = [
        _frame(0.0, right_wrist={"y": 0.1, "z": 0.0}),
        _frame(0.1, right_wrist={"y": 0.1, "z": 0.3}),  # バックスイング最深点（後方）
        _frame(0.2, right_wrist={"y": 0.1, "z": 0.1}),
        _frame(0.3, right_wrist={"y": 0.1, "z": -0.6}),  # コンタクト直前の急接近＝速度ピーク
        _frame(0.4, right_wrist={"y": 0.1, "z": -0.65}),
        _frame(0.5, right_wrist={"y": 0.1, "z": -0.66}),  # フォロー：速度低下
    ]
    result = detect_groundstroke(window, "right")
    assert result is not None
    assert result["backswing_end"]["t"] == 0.1
    assert result["contact"]["t"] == 0.3
    assert result["follow_end"]["t"] in (0.4, 0.5)


def test_detect_volley_finds_contact_as_most_forward_point():
    window = [
        _frame(0.0, right_wrist={"z": 0.1}),
        _frame(0.1, right_wrist={"z": -0.3}),
        _frame(0.2, right_wrist={"z": -0.6}),  # 最も前方＝コンタクト
        _frame(0.3, right_wrist={"z": -0.2}),
        _frame(0.4, right_wrist={"z": 0.0}),
    ]
    result = detect_volley(window, "right")
    assert result is not None
    assert result["punch_start"]["t"] == 0.0
    assert result["contact"]["t"] == 0.2
