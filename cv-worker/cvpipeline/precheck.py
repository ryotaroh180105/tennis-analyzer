"""precheck（CPU、GPU起動前。03/10のRound2修正: 高価な工程の前に安価に不合格を弾く）。

先頭60秒のメタデータ検査＋簡易コート検出を行い、matches.preflight_report を作る。
"""

import math

from cvpipeline.config_loader import load_precheck_params
from cvpipeline.stages.stage1_court import detect_court
from cvpipeline.video_io import ffprobe, sample_frames


def _check_coverage(court: dict, meta: dict, params: dict) -> dict:
    """画角カバレッジ（03 §プリフライトチェック）。

    厳密には「遠側2隅＋サイドラインの消失点が画面内か」だが、消失点の推定は
    別途複雑な幾何計算が要る。ここではdetect_courtが既に推定した
    court_polygon_px（[top-left, top-right, bottom-right, bottom-left]の順、
    stage1_court._extreme_corners参照）のうち画面上側＝遠い2隅が画面内に
    収まっているかで近似する（簡易プロキシ）。
    """
    if not court.get("court_detected") or not court.get("court_polygon_px"):
        # コート自体を検出できていない場合、画角カバレッジは判定不能（courtチェック側で
        # 縮退モードとして既に扱われる）。過度な断定を避けunknown扱いにする（不変原則1）。
        return {"result": "unknown", "value": None, "message": "coverage not assessable — court not detected"}

    w, h = meta["width"], meta["height"]
    margin = params["coverage"]["frame_margin_ratio"]
    far_corners = court["court_polygon_px"][:2]  # top-left, top-right

    out_of_frame = any(
        x < -w * margin or x > w * (1 + margin) or y < -h * margin or y > h * (1 + margin) for x, y in far_corners
    )
    return {
        "result": "warn" if out_of_frame else "ok",
        "value": far_corners,
        "message": "far court corners may be out of frame" if out_of_frame else "coverage ok",
    }


def _check_stability(frames: list, params: dict) -> dict:
    """カメラ固定（03 §プリフライトチェック）。フレーム間のグローバルモーションを
    位相相関（cv2.phaseCorrelate）で推定する。"""
    import cv2
    import numpy as np

    if len(frames) < 2:
        return {"result": "unknown", "value": None, "message": "stability not assessable — too few frames"}

    diag = math.sqrt(frames[0].shape[0] ** 2 + frames[0].shape[1] ** 2)
    shifts = []
    prev_gray = None
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev_gray is not None:
            (dx, dy), _ = cv2.phaseCorrelate(prev_gray, gray)
            shifts.append(math.sqrt(dx * dx + dy * dy))
        prev_gray = gray

    avg_shift_ratio = (sum(shifts) / len(shifts)) / diag if shifts and diag > 0 else 0.0
    is_unstable = avg_shift_ratio > params["stability"]["max_shift_ratio"]
    return {
        "result": "warn" if is_unstable else "ok",
        "value": round(avg_shift_ratio, 4),
        "message": "camera movement detected — try to keep it fixed" if is_unstable else "stability ok",
    }


def _check_brightness(frames: list, params: dict) -> dict:
    """明るさ/逆光（03 §プリフライトチェック）。輝度ヒストグラムの平均で近似する。"""
    import cv2

    if not frames:
        return {"result": "unknown", "value": None, "message": "brightness not assessable — no frames"}

    means = [float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()) for frame in frames]
    avg = sum(means) / len(means)
    too_dark = avg < params["brightness"]["min_mean"]
    too_bright = avg > params["brightness"]["max_mean"]
    return {
        "result": "warn" if (too_dark or too_bright) else "ok",
        "value": round(avg, 1),
        "message": "video is too dark or backlit" if too_dark or too_bright else "brightness ok",
    }


def run_precheck(video_path: str) -> dict:
    params = load_precheck_params()
    meta = ffprobe(video_path)

    checks: dict[str, dict] = {}

    if meta["duration_s"] <= 0:
        return {
            "input_valid": False,
            "reason": "unreadable or zero-duration video",
            "checks": checks,
            "degraded": False,
            "meta": meta,
        }

    sample_seconds = min(60.0, meta["duration_s"])

    court = detect_court(video_path, sample_seconds=sample_seconds)
    ok_min = params["court_confidence"]["ok_min"]
    warn_min = params["court_confidence"]["warn_min"]
    court_result = "ok" if court["confidence"] >= ok_min else ("warn" if court["confidence"] >= warn_min else "fail")
    checks["court"] = {
        "result": court_result,
        "value": court["confidence"],
        "message": "court detected" if court_result != "fail" else "court not detected — falling back to degraded mode",
    }

    degraded = court_result == "fail"

    res_ok = meta["width"] >= params["resolution"]["min_width"] and meta["height"] >= params["resolution"]["min_height"]
    checks["resolution"] = {
        "result": "ok" if res_ok else "warn",
        "value": f"{meta['width']}x{meta['height']}",
        "message": "resolution ok" if res_ok else "resolution below recommended 720p",
    }

    fps_ok = meta["fps"] >= params["framerate"]["min_fps"]
    checks["framerate"] = {
        "result": "ok" if fps_ok else "warn",
        "value": meta["fps"],
        "message": "fps ok" if fps_ok else "fps below recommended 24fps",
    }

    is_portrait = meta["height"] > meta["width"] if meta["rotation"] in (0, 180) else meta["width"] > meta["height"]
    checks["orientation"] = {
        "result": "warn" if is_portrait else "ok",
        "value": "portrait" if is_portrait else "landscape",
        "message": "portrait video — coverage may be reduced" if is_portrait else "landscape ok",
    }

    checks["coverage"] = _check_coverage(court, meta, params)

    sampled_frames = [f for _, f in sample_frames(video_path, hz=params["stability"]["sample_hz"], max_seconds=sample_seconds)]
    checks["stability"] = _check_stability(sampled_frames, params)
    checks["brightness"] = _check_brightness(sampled_frames, params)

    return {
        "input_valid": True,
        "checks": checks,
        "degraded": degraded,
        "sampled_range_s": [0, sample_seconds],
        "meta": meta,
        "court": court,
    }
