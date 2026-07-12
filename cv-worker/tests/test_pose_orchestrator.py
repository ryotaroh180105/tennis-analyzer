"""フォーム解析オーケストレーションの結合テスト（12-form-analysis.md）。

extract_landmarks（実MediaPipe呼び出し）は実動画・モデルが要るため対象外とし、
合成ランドマーク系列でanalyze_landmarksの挙動を検証する。後半は実際の
config/shot-mechanics.v1.yamlを読み込んで通しで動くことを確認する結合テスト。
"""

from cvpipeline.config_loader import load_shot_mechanics
from cvpipeline.pose.orchestrator import analyze_landmarks


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


def _forehand_series(n_swings: int, dt: float = 0.1, gap_s: float = 3.0):
    """n_swings回のフォアハンド様スイングを持つ合成系列（右利き想定）。"""
    series = []
    t = 0.0
    for _ in range(n_swings):
        # 静止区間
        for _ in range(5):
            joints = _neutral_joints()
            series.append({"t": round(t, 2), "joints": joints, "visible_ratio": 0.9})
            t += dt
        # バックスイング（後方へ）
        joints = _neutral_joints()
        joints["right_wrist"]["z"] = 0.4
        series.append({"t": round(t, 2), "joints": joints, "visible_ratio": 0.9})
        t += dt
        # 急接近（コンタクト、速度ピーク）
        joints = _neutral_joints()
        joints["right_wrist"]["z"] = -0.8
        series.append({"t": round(t, 2), "joints": joints, "visible_ratio": 0.9})
        t += dt
        # フォロースルー（速度低下）
        for z in (-0.85, -0.87):
            joints = _neutral_joints()
            joints["right_wrist"]["z"] = z
            series.append({"t": round(t, 2), "joints": joints, "visible_ratio": 0.9})
            t += dt
        t += gap_s  # スイング間の間隔（min_interval_sを超える）
    return series


def _custom_config():
    return {
        "citation_status": "test",
        "defaults": {"min_landmark_visibility": 0.6, "max_feedback_metrics": 3},
        "swing_detection": {
            "min_peak_speed_mps": 3.0,
            "min_interval_s": 1.0,
            "window_pre_s": 0.5,
            "window_post_s": 0.5,
            "min_valid_swings": 3,
        },
        "shots": {
            "forehand": {
                "detector": "groundstroke",
                "metrics": [
                    {
                        "id": "elbow_angle_at_contact",
                        "at": "contact",
                        "primitive": "joint_angle",
                        "args": {"points": ["dominant_shoulder", "dominant_elbow", "dominant_wrist"]},
                        "unit": "deg",
                        "elite_range": [110, 165],
                        "tolerance": 15,
                        "advice_key": "arm_structure",
                    },
                    {
                        "id": "backswing_to_contact_ms",
                        "at": "contact",
                        "primitive": "event_interval",
                        "args": {"from_event": "backswing_end", "to_event": "contact"},
                        "unit": "ms",
                        "elite_range": [250, 450],
                        "tolerance": 80,
                        "advice_key": "swing_tempo",
                    },
                ],
            }
        },
    }


def test_analyze_landmarks_insufficient_data_below_min_swings():
    series = _forehand_series(n_swings=1)
    result = analyze_landmarks(series, "forehand", config=_custom_config())
    assert result["insufficient_data"] is True
    assert result["feedback_metrics"] == []


def test_analyze_landmarks_aggregates_across_swings():
    series = _forehand_series(n_swings=3)
    result = analyze_landmarks(series, "forehand", config=_custom_config())
    assert result["insufficient_data"] is False
    assert result["swing_count"] == 3
    assert result["dominant_side"] == "right"

    timing = next(m for m in result["metrics"] if m["id"] == "backswing_to_contact_ms")
    assert timing["measured"] is not None
    assert timing["valid_swings"] == 3


def test_analyze_landmarks_loads_real_shot_mechanics_config_for_forehand():
    """実際のconfig/shot-mechanics.v1.yamlを読み込んで通しで動くことを確認する結合テスト。"""
    config = load_shot_mechanics()
    series = _forehand_series(n_swings=3, gap_s=4.0)  # 実configはmin_interval_s=1.5
    result = analyze_landmarks(series, "forehand", backhand_style=None, config=config)
    assert result["shot_type"] == "forehand"
    assert isinstance(result["metrics"], list)
    assert len(result["metrics"]) == 5  # forehandセクションの指標数
    assert result["citation_status"] == "placeholder_pending_literature_review"


def test_analyze_landmarks_real_config_for_backhand_one_handed():
    config = load_shot_mechanics()
    series = _forehand_series(n_swings=3, gap_s=4.0)
    result = analyze_landmarks(series, "backhand", backhand_style="one_handed", config=config)
    assert result["shot_type"] == "backhand"
    assert result["swing_count"] == 3
    assert len(result["metrics"]) == 6  # backhandセクションのone_handed対象指標数

    direction = next(m for m in result["metrics"] if m["id"] == "shoulder_hip_separation_direction_at_contact")
    assert direction["elite_range"] is None
    assert direction["expected_sign"] == "positive"
    assert direction["status"] in {"in_range", "out_of_range", "unknown"}


def test_analyze_landmarks_real_config_for_backhand_two_handed():
    config = load_shot_mechanics()
    series = _forehand_series(n_swings=3, gap_s=4.0)
    result = analyze_landmarks(series, "backhand", backhand_style="two_handed", config=config)
    assert len(result["metrics"]) == 5  # backhandセクションのtwo_handed対象指標数（elbow_extension_at_contactは片手専用）

    direction = next(m for m in result["metrics"] if m["id"] == "shoulder_hip_separation_direction_at_contact_2h")
    assert direction["elite_range"] is None
    assert direction["expected_sign"] == "negative"


def _serve_like_series(n_swings: int, dt: float = 0.05, gap_s: float = 4.0):
    """n_swings回のサーブ/スマッシュ様スイングを持つ合成系列（右利き想定）。"""
    series = []
    t = 0.0
    for _ in range(n_swings):
        for left_y, right_y, right_knee_x in [
            (0.1, 0.1, 0.1),
            (-0.2, 0.1, 0.1),
            (-0.6, 0.1, 0.1),   # トス頂点
            (-0.4, -0.3, -0.3),  # トロフィー（left_kneeを曲げる）
            (-0.2, -1.2, 0.1),   # インパクト
            (0.0, -0.6, 0.1),
        ]:
            joints = _neutral_joints()
            joints["left_wrist"]["y"] = left_y
            joints["right_wrist"]["y"] = right_y
            joints["left_knee"]["x"] = right_knee_x
            series.append({"t": round(t, 2), "joints": joints, "visible_ratio": 0.9})
            t += dt
        t += gap_s
    return series


def _volley_series(n_swings: int, dt: float = 0.1, gap_s: float = 4.0):
    series = []
    t = 0.0
    for _ in range(n_swings):
        for z in (0.1, -0.2, -0.5, -0.6, -0.2, 0.0):
            joints = _neutral_joints()
            joints["right_wrist"]["z"] = z
            series.append({"t": round(t, 2), "joints": joints, "visible_ratio": 0.9})
            t += dt
        t += gap_s
    return series


def test_analyze_landmarks_real_config_for_smash():
    config = load_shot_mechanics()
    series = _serve_like_series(n_swings=3)
    result = analyze_landmarks(series, "smash", config=config)
    assert result["shot_type"] == "smash"
    assert result["swing_count"] == 3
    assert len(result["metrics"]) == 4  # smashセクションの指標数
    # smashは4指標とも文献未確認のためmeasured-onlyモード（13 A-3）。
    # レンジ比較をせず、注目ポイント（feedback_metrics）の対象にもならない。
    for metric in result["metrics"]:
        assert metric["elite_range"] is None
        assert metric["expected_sign"] is None
        assert metric["status"] in ("measured", "unknown")
    assert result["feedback_metrics"] == []


def test_analyze_landmarks_real_config_for_volley():
    config = load_shot_mechanics()
    series = _volley_series(n_swings=3)
    result = analyze_landmarks(series, "volley", config=config)
    assert result["shot_type"] == "volley"
    assert result["swing_count"] == 3
    assert len(result["metrics"]) == 3  # volleyセクションの指標数

    by_id = {m["id"]: m for m in result["metrics"]}
    # elbow_angle_delta_through_contact / contact_forward_of_body は文献未確認
    # のためmeasured-onlyモード（13 A-3）。knee_flexion_at_contactのみ実文献値
    # （Huang 2008）を持ち、レンジ比較の対象。
    assert by_id["elbow_angle_delta_through_contact"]["elite_range"] is None
    assert by_id["elbow_angle_delta_through_contact"]["status"] in ("measured", "unknown")
    assert by_id["contact_forward_of_body"]["elite_range"] is None
    assert by_id["contact_forward_of_body"]["status"] in ("measured", "unknown")
    assert by_id["knee_flexion_at_contact"]["elite_range"] == [155, 180]
