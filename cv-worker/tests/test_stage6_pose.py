"""ステージ6（サーブ骨格解析）の純粋関数テスト。extract_landmarks（実MediaPipe呼び出し）は
実動画・モデルファイルが要るため対象外とし、segment_phases/compute_metrics/rank_feedback_metrics
の合成ランドマークデータでの挙動のみを検証する（stage5と同じ方針、01 §Phase3）。"""

from cvpipeline.stages.stage6_pose import compute_metrics, rank_feedback_metrics, segment_phases


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


# 右腕でサーブを打つ合成シーケンス：左手首がトス(frame3で頂点)、右手首がframe7でインパクト
# （最高点）、左膝はframe5だけ曲げてトロフィーポーズを表現する。
_LEFT_WRIST_Y = [0.1, 0.1, -0.2, -0.6, -0.5, -0.3, -0.1, 0.0, 0.05, 0.1]
_RIGHT_WRIST_Y = [0.1, 0.1, 0.1, 0.1, -0.2, -0.5, -0.9, -1.6, -1.0, -0.5]


def _serve_landmark_series(visibility: float = 0.9) -> list[dict]:
    series = []
    for i in range(10):
        joints = _neutral_joints()
        joints["left_wrist"]["y"] = _LEFT_WRIST_Y[i]
        joints["right_wrist"]["y"] = _RIGHT_WRIST_Y[i]
        if i == 5:
            joints["left_knee"]["x"] = 0.25  # トロフィーポーズ：軸足の膝を曲げる
        for j in joints.values():
            j["visibility"] = visibility
        series.append({"t": round(i * 0.1, 2), "joints": joints, "visible_ratio": visibility})
    return series


def test_segment_phases_detects_dominant_side_and_key_frames():
    phases = segment_phases(_serve_landmark_series())
    assert phases["dominant_side"] == "right"
    assert phases["_frames"]["toss_apex"]["t"] == 0.3
    assert phases["_frames"]["trophy"]["t"] == 0.5
    assert phases["_frames"]["impact"]["t"] == 0.7
    assert phases["impact"]["start_s"] == 0.7
    assert phases["follow_through"]["end_s"] == 0.9


def test_segment_phases_returns_empty_with_too_few_valid_frames():
    series = [{"t": 0.0, "joints": None, "visible_ratio": 0.0}] * 3
    assert segment_phases(series) == {}


def _config():
    return {
        "min_landmark_visibility": 0.6,
        "max_feedback_metrics": 3,
        "metrics": [
            {
                "id": "toss_apex_to_impact_ms",
                "phase": "impact",
                "unit": "ms",
                "elite_range": [350, 550],
                "tolerance": 80,
                "advice_key": "toss_timing",
            },
            {
                "id": "knee_flexion_at_trophy",
                "phase": "trophy",
                "unit": "deg",
                "elite_range": [95, 120],
                "tolerance": 8,
                "advice_key": "knee_bend",
            },
        ],
    }


def test_compute_metrics_timing_metric_is_in_range():
    series = _serve_landmark_series()
    phases = segment_phases(series)
    metrics = compute_metrics(series, phases, _config())
    timing = next(m for m in metrics if m["id"] == "toss_apex_to_impact_ms")
    assert timing["measured"] == 400.0
    assert timing["status"] == "in_range"
    assert timing["confidence"] > 0


def test_compute_metrics_knee_flexion_uses_non_dominant_leg_at_trophy():
    series = _serve_landmark_series()
    phases = segment_phases(series)
    metrics = compute_metrics(series, phases, _config())
    knee = next(m for m in metrics if m["id"] == "knee_flexion_at_trophy")
    assert knee["measured"] is not None
    assert 90 <= knee["measured"] <= 130
    assert knee["status"] in ("in_range", "borderline")


def test_compute_metrics_low_visibility_yields_unknown_status():
    series = _serve_landmark_series(visibility=0.1)  # min_landmark_visibility=0.6を下回る
    phases = segment_phases(series)
    metrics = compute_metrics(series, phases, _config())
    for m in metrics:
        assert m["status"] == "unknown"
        assert m["measured"] is None
        assert m["confidence"] == 0.0


def test_compute_metrics_no_phases_returns_empty_list():
    assert compute_metrics([], {}, _config()) == []


def test_rank_feedback_metrics_only_out_of_range_sorted_by_deviation():
    metrics = [
        {"id": "a", "status": "in_range", "measured": 100, "elite_range": [90, 110]},
        {"id": "b", "status": "out_of_range", "measured": 200, "elite_range": [90, 110]},  # deviation 90
        {"id": "c", "status": "out_of_range", "measured": 130, "elite_range": [90, 110]},  # deviation 20
        {"id": "d", "status": "unknown", "measured": None, "elite_range": [90, 110]},
    ]
    ranked = rank_feedback_metrics(metrics, max_metrics=3)
    assert [m["id"] for m in ranked] == ["b", "c"]


def test_rank_feedback_metrics_respects_max_metrics_cap():
    metrics = [
        {"id": f"m{i}", "status": "out_of_range", "measured": 100 + i * 10, "elite_range": [0, 50]}
        for i in range(5)
    ]
    ranked = rank_feedback_metrics(metrics, max_metrics=2)
    assert len(ranked) == 2
