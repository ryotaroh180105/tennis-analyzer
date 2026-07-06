"""precheck（CPU、GPU起動前。03/10のRound2修正: 高価な工程の前に安価に不合格を弾く）。

先頭60秒のメタデータ検査＋簡易コート検出を行い、matches.preflight_report を作る。
"""

from cvpipeline.stages.stage1_court import detect_court
from cvpipeline.video_io import ffprobe

# 03 §プリフライトチェックのしきい値（暫定値。将来configへ外出しする余地あり）
MIN_RESOLUTION = (960, 540)  # 720p未満は警告
MIN_FPS = 20.0


def run_precheck(video_path: str) -> dict:
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

    court = detect_court(video_path, sample_seconds=min(60.0, meta["duration_s"]))
    court_result = "ok" if court["confidence"] >= 0.5 else ("warn" if court["confidence"] >= 0.2 else "fail")
    checks["court"] = {
        "result": court_result,
        "value": court["confidence"],
        "message": "court detected" if court_result != "fail" else "court not detected — falling back to degraded mode",
    }

    degraded = court_result == "fail"

    res_ok = meta["width"] >= MIN_RESOLUTION[0] and meta["height"] >= MIN_RESOLUTION[1]
    checks["resolution"] = {
        "result": "ok" if res_ok else "warn",
        "value": f"{meta['width']}x{meta['height']}",
        "message": "resolution ok" if res_ok else "resolution below recommended 720p",
    }

    fps_ok = meta["fps"] >= MIN_FPS
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

    return {
        "input_valid": True,
        "checks": checks,
        "degraded": degraded,
        "sampled_range_s": [0, min(60.0, meta["duration_s"])],
        "meta": meta,
        "court": court,
    }
