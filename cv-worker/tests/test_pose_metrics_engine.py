"""指標評価・集約の純粋関数テスト（12-form-analysis.md §指標エンジン／集約は中央値+IQR）。"""

from cvpipeline.pose.metrics_engine import (
    aggregate_metric,
    evaluate_metric,
    evaluate_qualitative_status,
    evaluate_status,
)


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


def test_evaluate_qualitative_status_matches_expected_sign():
    assert evaluate_qualitative_status(12.0, "positive") == "in_range"
    assert evaluate_qualitative_status(-12.0, "positive") == "out_of_range"
    assert evaluate_qualitative_status(-12.0, "negative") == "in_range"
    assert evaluate_qualitative_status(0.0, "positive") == "out_of_range"


def _qualitative_metric(**overrides):
    metric = _metric(
        id="separation_direction",
        primitive="line_separation_signed",
        expected_sign="positive",
        advice_key="unit_turn",
    )
    del metric["elite_range"]
    del metric["tolerance"]
    metric.update(overrides)
    return metric


def test_aggregate_metric_qualitative_mode_has_no_elite_range():
    metric = _qualitative_metric()
    result = aggregate_metric(metric, [10.0, 12.0, 8.0])
    assert result["elite_range"] is None
    assert result["expected_sign"] == "positive"
    assert result["status"] == "in_range"
    assert result["measured"] == 10.0


def test_aggregate_metric_qualitative_mode_out_of_range_when_sign_mismatches():
    metric = _qualitative_metric(expected_sign="negative")
    result = aggregate_metric(metric, [10.0, 12.0, 8.0])
    assert result["status"] == "out_of_range"


def test_aggregate_metric_qualitative_mode_high_variance_when_signs_disagree():
    metric = _qualitative_metric()
    result = aggregate_metric(metric, [10.0, -5.0, 8.0])
    assert result["high_variance"] is True


def test_aggregate_metric_qualitative_mode_no_valid_swings_is_unknown():
    result = aggregate_metric(_qualitative_metric(), [])
    assert result["status"] == "unknown"
    assert result["elite_range"] is None


def _measured_only_metric(**overrides):
    metric = _metric(id="contact_height_relative", advice_key="contact_height")
    del metric["elite_range"]
    del metric["tolerance"]
    metric.update(overrides)
    return metric


def test_aggregate_metric_measured_only_mode_has_no_range_or_sign():
    # 13 A-3: elite_rangeもexpected_signも無い指標はレンジ比較をせず"measured"を返す
    # （文献未確認の指標に推測レンジを割り当てないための状態）
    result = aggregate_metric(_measured_only_metric(), [100.0, 105.0, 95.0])
    assert result["status"] == "measured"
    assert result["elite_range"] is None
    assert result["expected_sign"] is None
    assert result["measured"] == 100.0
    assert result["valid_swings"] == 3


def test_aggregate_metric_measured_only_mode_no_valid_swings_is_unknown():
    result = aggregate_metric(_measured_only_metric(), [])
    assert result["status"] == "unknown"
    assert result["elite_range"] is None


def test_aggregate_metric_measured_only_mode_still_flags_high_variance_via_cv_max():
    # レンジは無くてもconsistency_cv_maxがあれば「ばらつき大」判定は独立して機能する
    metric = _measured_only_metric(consistency_cv_max=0.1)
    result = aggregate_metric(metric, [100.0, 200.0, 100.0])
    assert result["status"] == "measured"
    assert result["high_variance"] is True
