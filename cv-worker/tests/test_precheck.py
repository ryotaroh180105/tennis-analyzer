"""precheckの追加チェック（画角カバレッジ・カメラ固定・明るさ）のテスト
（03 §プリフライトチェック、設計レビュー13 E'）。"""

import numpy as np
import pytest

from cvpipeline.config_loader import load_precheck_params
from cvpipeline.precheck import _check_brightness, _check_coverage, _check_stability, run_precheck


@pytest.fixture
def params():
    return load_precheck_params()


def _solid_frame(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def _noise_frame(h: int, w: int, seed: int = 0) -> np.ndarray:
    # phaseCorrelateは周期的な模様（市松等）だと自己相関があいまいになり誤検出するため、
    # 無地/低テクスチャの静止フレームの代わりに非周期なノイズテクスチャを使う。
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)


def test_check_coverage_ok_when_far_corners_within_frame(params):
    court = {
        "court_detected": True,
        "court_polygon_px": [[100.0, 40.0], [540.0, 40.0], [540.0, 320.0], [100.0, 320.0]],
    }
    meta = {"width": 640, "height": 360}
    result = _check_coverage(court, meta, params)
    assert result["result"] == "ok"


def test_check_coverage_warns_when_far_corner_outside_frame(params):
    court = {
        "court_detected": True,
        "court_polygon_px": [[-200.0, -100.0], [540.0, 40.0], [540.0, 320.0], [100.0, 320.0]],
    }
    meta = {"width": 640, "height": 360}
    result = _check_coverage(court, meta, params)
    assert result["result"] == "warn"


def test_check_coverage_unknown_when_court_not_detected(params):
    court = {"court_detected": False, "court_polygon_px": None}
    meta = {"width": 640, "height": 360}
    result = _check_coverage(court, meta, params)
    assert result["result"] == "unknown"


def test_check_stability_ok_for_static_frames(params):
    base = _noise_frame(120, 160)
    frames = [base for _ in range(5)]  # 完全に同一フレーム＝カメラ動き無し
    result = _check_stability(frames, params)
    assert result["result"] == "ok"


def test_check_stability_warns_for_shifting_frames(params):
    base = _noise_frame(120, 160)
    # フレームごとに水平方向へ大きくシフト＝グローバルモーションが大きい状態を模擬
    frames = [np.roll(base, shift=i * 15, axis=1) for i in range(5)]
    result = _check_stability(frames, params)
    assert result["result"] == "warn"


def test_check_stability_unknown_for_too_few_frames(params):
    result = _check_stability([_noise_frame(120, 160)], params)
    assert result["result"] == "unknown"


def test_check_brightness_ok_for_mid_gray(params):
    frames = [_solid_frame(120, 160, 128) for _ in range(3)]
    result = _check_brightness(frames, params)
    assert result["result"] == "ok"


def test_check_brightness_warns_when_too_dark(params):
    frames = [_solid_frame(120, 160, 5) for _ in range(3)]
    result = _check_brightness(frames, params)
    assert result["result"] == "warn"


def test_check_brightness_warns_when_too_bright(params):
    frames = [_solid_frame(120, 160, 250) for _ in range(3)]
    result = _check_brightness(frames, params)
    assert result["result"] == "warn"


def test_check_brightness_unknown_for_no_frames(params):
    result = _check_brightness([], params)
    assert result["result"] == "unknown"


def test_run_precheck_includes_new_checks_on_synthetic_video(synthetic_video):
    report = run_precheck(synthetic_video)
    assert report["input_valid"] is True
    assert set(report["checks"].keys()) == {
        "court",
        "resolution",
        "framerate",
        "orientation",
        "coverage",
        "stability",
        "brightness",
    }
    # 合成動画は固定カメラで明るさも中庸なので、少なくともstability/brightnessはok想定
    assert report["checks"]["stability"]["result"] == "ok"
    assert report["checks"]["brightness"]["result"] == "ok"
