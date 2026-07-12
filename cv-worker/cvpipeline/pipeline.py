"""stage1-4を統括し、event_streams payload と初期segmentsを組み立てる（analyzeジョブの中身）。"""

import time

from cvpipeline.stages.stage1_court import detect_court
from cvpipeline.stages.stage2_players import analyze_person_motion
from cvpipeline.stages.stage3_ball import analyze_ball_motion
from cvpipeline.stages.stage4_segments import segment_points
from cvpipeline.stages.stage5_shots import detect_shots
from cvpipeline.video_io import ffprobe

ANALYSIS_HZ = 5  # config/segmentation.v1.yaml sampling.base_hz と一致させる


def run_analyze(video_path: str, degraded: bool) -> dict:
    """戻り値: {"event_stream_payload": {...}, "segments": [{"start_s","end_s","confidence"}],
    "stage_seconds": {"stage1_s"..."stage5_s"}}

    stage_seconds はステージ別GPU秒の原価計測に使う（08 §運用「初日から」・10 §metrics契約
    breakdown: {..., stage1_s..stage4_s, ...}。設計レビュー13 D-1で判明した欠落分の追加）。
    """
    meta = ffprobe(video_path)
    stage_seconds: dict[str, float] = {}

    t0 = time.monotonic()
    court = (
        {"court_detected": False, "homography": None, "court_polygon_px": None, "confidence": 0.0}
        if degraded
        else detect_court(video_path, sample_seconds=min(60.0, meta["duration_s"]))
    )
    stage_seconds["stage1_s"] = round(time.monotonic() - t0, 2)

    t0 = time.monotonic()
    person_result = analyze_person_motion(
        video_path,
        court.get("court_polygon_px"),
        hz=ANALYSIS_HZ,
        max_seconds=None,
        degraded=degraded,
    )
    stage_seconds["stage2_s"] = round(time.monotonic() - t0, 2)

    t0 = time.monotonic()
    ball_result = (
        {"hz": ANALYSIS_HZ, "per_frame": [], "confidence": 0.0}
        if degraded
        else analyze_ball_motion(video_path, hz=ANALYSIS_HZ, max_seconds=None)
    )
    stage_seconds["stage3_s"] = round(time.monotonic() - t0, 2)

    t0 = time.monotonic()
    seg_result = segment_points(person_result, ball_result, degraded=degraded, duration_s=meta["duration_s"])
    stage_seconds["stage4_s"] = round(time.monotonic() - t0, 2)

    t0 = time.monotonic()
    shots_by_point = detect_shots(seg_result["segments"], ball_result, degraded=degraded)
    stage_seconds["stage5_s"] = round(time.monotonic() - t0, 2)

    overall_confidence = (
        0.4 * court.get("confidence", 0.0)
        + 0.4 * person_result.get("confidence", 0.0)
        + 0.2 * ball_result.get("confidence", 0.0)
    )

    event_stream_payload = {
        "video": {
            "duration_s": meta["duration_s"],
            "fps": meta["fps"],
            "resolution": f"{meta['width']}x{meta['height']}",
        },
        "court": {
            "type": court.get("court_type", "unknown"),
            "homography": court.get("homography"),
            "confidence": court.get("confidence", 0.0),
        }
        if court.get("court_detected")
        else None,
        "points": [
            {
                "index": i,
                "clip": {"start_s": s["start_s"], "end_s": s["end_s"]},
                "confidence": s["confidence"],
                "shots": shots_by_point[i],
                "shot_count": len(shots_by_point[i]),
            }
            for i, s in enumerate(seg_result["segments"])
        ],
        "confidence": {
            "overall": round(overall_confidence, 3),
            "degraded": degraded,
        },
    }

    return {
        "event_stream_payload": event_stream_payload,
        "segments": seg_result["segments"],
        "degraded": degraded,
        "stage_seconds": stage_seconds,
    }
