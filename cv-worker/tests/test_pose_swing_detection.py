"""スイング自動分割の純粋関数テスト（12-form-analysis.md §1動画=複数スイング前提）。"""

from cvpipeline.pose.swing_detection import detect_swing_peaks, split_swings


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


def _two_swing_series():
    """40フレーム(dt=0.1s)。右手首がt≈0.6とt≈2.6付近で速く動く2回のスイング。"""
    series = []
    right_wrist_y = {6: -0.8, 7: -1.2, 26: -0.8, 27: -1.2}
    for i in range(40):
        joints = _neutral_joints()
        joints["right_wrist"]["y"] = right_wrist_y.get(i, 0.1)
        series.append({"t": round(i * 0.1, 2), "joints": joints, "visible_ratio": 0.9})
    return series


def _config():
    return {"min_peak_speed_mps": 3.0, "min_interval_s": 1.0, "window_pre_s": 0.3, "window_post_s": 0.2}


def test_detect_swing_peaks_finds_two_distinct_swings():
    peaks = detect_swing_peaks(_two_swing_series(), "right", _config())
    assert len(peaks) == 2
    t0, t1 = peaks[0][0], peaks[1][0]
    assert 0.5 <= t0 <= 0.8
    assert 2.5 <= t1 <= 2.8


def test_detect_swing_peaks_merges_close_peaks_within_min_interval():
    # min_intervalを大きくすると2回のスイングが1回に併合される
    config = dict(_config(), min_interval_s=5.0)
    peaks = detect_swing_peaks(_two_swing_series(), "right", config)
    assert len(peaks) == 1


def test_detect_swing_peaks_ignores_slow_motion():
    config = dict(_config(), min_peak_speed_mps=100.0)
    peaks = detect_swing_peaks(_two_swing_series(), "right", config)
    assert peaks == []


def test_split_swings_returns_one_window_per_peak():
    windows = split_swings(_two_swing_series(), "right", _config())
    assert len(windows) == 2
    for window in windows:
        assert len(window) > 0


def test_split_swings_windows_are_bounded_by_pre_post_config():
    config = dict(_config(), window_pre_s=0.15, window_post_s=0.05)
    windows = split_swings(_two_swing_series(), "right", config)
    first = windows[0]
    duration = first[-1]["t"] - first[0]["t"]
    assert duration <= 0.15 + 0.05 + 0.01  # 端数許容
