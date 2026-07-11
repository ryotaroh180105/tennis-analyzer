"""指標評価・集約の純粋関数テスト（12-form-analysis.md §指標エンジン／集約は中央値+IQR）。"""

from cvpipeline.pose.metrics_engine import aggregate_metric, evaluate_metric, evaluate_status


def _neutral_joints():
    return {
        "left_shoulder": {"x": -0.2, "y": -0.5, "z": 0.0, "visibility": 0.9},
        "right_shoulder": {"x": 0.2, "y": -0.5, "z": 0.0, "visibility": 0.9},
        "left_hip": {"x": -0.1, "y": 0.0, "z": 0.0, "visibility": 0.9},
        "right_hip": {"x": 0.1, "y": 0.0, "z": 0.0, "visibility": 0.9},
        "left_knee": {"x": -0.1, "y": 0.5, "z": 0.0, "visibility": 0.9},
        "right_knee": {"x": 0.1, "y": 0.5, "z": 0.0, "visibility": 0.9},
        "left_ankle": {"x": -0.1, "y": 1.0, "z": 0.0, "visibility": 0.9},
        "right_ankle": {"x": 0.1, "y": 1.0, "z": 0.0, "visibility": 0.9},
    }


def _metric(**overrides):
    base = {
        "id": "knee_flexion",
        "at": "trophy",
        "primitive": "joint_angle",
        "args": {"points": ["nondominant_hip", "nondominant_knee", "nondominant_ankle"]},
        "unit": "deg",
        "elite_range": [95, 120],
        "tolerance": 8,
        "advice_key": "knee_bend",
    }
    base.update(overrides)
    return base


def test_evaluate_metric_computes_value_when_visibility_ok():
    frames_by_event = {"trophy": {"t": 0.3, "joints": _neutral_joints(), "visible_ratio": 0.9}}
    result = evaluate_metric(_metric(), frames_by_event, "right", 0.6, None)
    assert result["value"] == 180.0  # 直立姿勢のneutral_jointsは膝が伸びている
    assert result["confidence"] > 0


def test_evaluate_metric_low_visibility_returns_no_value():
    frames_by_event = {"trophy": {"t": 0.3, "joints": _neutral_joints(), "visible_ratio": 0.1}}
    result = evaluate_metric(_metric(), frames_by_event, "right", 0.6, None)
    assert result["value"] is None
    assert result["confidence"] == 0.0


def test_evaluate_metric_missing_event_returns_no_value():
    result = evaluate_metric(_metric(), {}, "right", 0.6, None)
    assert result["value"] is None


def test_evaluate_metric_only_style_filters_out_non_matching_swing():
    metric = _metric(only_style="two_handed")
    frames_by_event = {"trophy": {"t": 0.3, "joints": _neutral_joints(), "visible_ratio": 0.9}}
    assert evaluate_metric(metric, frames_by_event, "right", 0.6, "one_handed") is None
    assert evaluate_metric(metric, frames_by_event, "right", 0.6, "two_handed") is not None


def test_evaluate_status_bands():
    assert evaluate_status(105, [95, 120], 8) == "in_range"
    assert evaluate_status(125, [95, 120], 8) == "borderline"  # 120+8=128の範囲内
    assert evaluate_status(140, [95, 120], 8) == "out_of_range"


def test_aggregate_metric_uses_median_and_flags_high_variance():
    metric = _metric(consistency_cv_max=0.1)
    values = [100.0, 200.0, 100.0]  # 中央値100、大きなばらつき
    result = aggregate_metric(metric, values)
    assert result["measured"] == 100.0
    assert result["valid_swings"] == 3
    assert result["high_variance"] is True


def test_aggregate_metric_no_valid_swings_is_unknown():
    result = aggregate_metric(_metric(), [])
    assert result["status"] == "unknown"
    assert result["measured"] is None
    assert result["valid_swings"] == 0
