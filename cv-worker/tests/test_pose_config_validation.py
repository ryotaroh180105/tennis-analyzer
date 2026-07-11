"""shot-mechanics.v1.yaml ロード時スキーマ検証のテスト（13 A-1）。"""

import copy

import pytest

from cvpipeline.config_loader import load_shot_mechanics
from cvpipeline.pose.config_validation import validate_shot_mechanics


def _valid_config() -> dict:
    return {
        "version": 1,
        "citation_status": "placeholder_pending_literature_review",
        "defaults": {"min_landmark_visibility": 0.6, "max_feedback_metrics": 3},
        "swing_detection": {
            "min_peak_speed_mps": 3.0,
            "min_interval_s": 1.5,
            "window_pre_s": 1.5,
            "window_post_s": 1.0,
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
                        "source": "placeholder",
                    },
                    {
                        "id": "separation_direction",
                        "at": "contact",
                        "primitive": "line_separation_signed",
                        "args": {"lines": ["shoulder_line", "hip_line"]},
                        "unit": "deg",
                        "expected_sign": "positive",
                        "advice_key": "unit_turn",
                        "source": "placeholder",
                    },
                    {
                        "id": "measured_only_metric",
                        "at": "contact",
                        "primitive": "forward_of_body",
                        "args": {"point": "dominant_wrist"},
                        "unit": "relative_torso",
                        "advice_key": "contact_point",
                        "source": "placeholder",
                    },
                ],
            }
        },
    }


def test_validate_shot_mechanics_accepts_well_formed_config():
    validate_shot_mechanics(_valid_config())  # raises on failure


def test_validate_shot_mechanics_rejects_unknown_role():
    cfg = _valid_config()
    cfg["shots"]["forehand"]["metrics"][0]["args"]["points"][0] = "dominant_head"
    with pytest.raises(ValueError, match="unsupported joint role"):
        validate_shot_mechanics(cfg)


def test_validate_shot_mechanics_rejects_unknown_event():
    cfg = _valid_config()
    cfg["shots"]["forehand"]["metrics"][0]["at"] = "backswing_start"  # groundstrokeが出さないイベント名
    with pytest.raises(ValueError, match="unknown event"):
        validate_shot_mechanics(cfg)


def test_validate_shot_mechanics_rejects_unknown_primitive():
    cfg = _valid_config()
    cfg["shots"]["forehand"]["metrics"][0]["primitive"] = "joint_angel"  # typo
    with pytest.raises(ValueError, match="unknown primitive"):
        validate_shot_mechanics(cfg)


def test_validate_shot_mechanics_rejects_unknown_detector():
    cfg = _valid_config()
    cfg["shots"]["forehand"]["detector"] = "swing"  # 実際は groundstroke
    with pytest.raises(ValueError, match="unknown detector"):
        validate_shot_mechanics(cfg)


def test_validate_shot_mechanics_rejects_elite_range_and_expected_sign_together():
    cfg = _valid_config()
    cfg["shots"]["forehand"]["metrics"][0]["expected_sign"] = "positive"
    with pytest.raises(ValueError, match="排他"):
        validate_shot_mechanics(cfg)


def test_validate_shot_mechanics_rejects_elite_range_without_tolerance():
    cfg = _valid_config()
    del cfg["shots"]["forehand"]["metrics"][0]["tolerance"]
    with pytest.raises(ValueError, match="tolerance"):
        validate_shot_mechanics(cfg)


def test_validate_shot_mechanics_rejects_invalid_expected_sign_value():
    cfg = _valid_config()
    cfg["shots"]["forehand"]["metrics"][1]["expected_sign"] = "up"
    with pytest.raises(ValueError, match="expected_sign"):
        validate_shot_mechanics(cfg)


def test_validate_shot_mechanics_rejects_invalid_only_style():
    cfg = _valid_config()
    cfg["shots"]["forehand"]["metrics"][0]["only_style"] = "no_handed"
    with pytest.raises(ValueError, match="only_style"):
        validate_shot_mechanics(cfg)


def test_validate_shot_mechanics_accepts_metric_without_range_or_sign():
    # 測定値のみモード（13 A-3）: elite_range も expected_sign も無いのは正当な状態
    cfg = _valid_config()
    validate_shot_mechanics(cfg)
    assert "elite_range" not in cfg["shots"]["forehand"]["metrics"][2]
    assert "expected_sign" not in cfg["shots"]["forehand"]["metrics"][2]


def test_load_shot_mechanics_real_config_is_valid():
    # load_shot_mechanics() 自体が呼び出し時にvalidate_shot_mechanicsを通す。
    validate_shot_mechanics(copy.deepcopy(load_shot_mechanics()))
