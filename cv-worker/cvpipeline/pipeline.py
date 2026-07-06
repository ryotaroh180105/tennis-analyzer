"""stage1-4を統括し、event_streams payload と初期segmentsを組み立てる（analyzeジョブの中身）。"""

from cvpipeline.stages.stage1_court import detect_court
from cvpipeline.stages.stage2_players import analyze_person_motion
from cvpipeline.stages.stage3_ball import analyze_ball_motion
from cvpipeline.stages.stage4_segments import segment_points
from cvpipeline.video_io import ffprobe

ANALYSIS_HZ = 5  # config/segmentation.v1.yaml sampling.base_hz と一致させる


def run_analyze(video_path: str, degraded: bool) -> dict:
    """戻り値: {"event_stream_payload": {...}, "segments": [{"start_s","end_s","confidence"}]}"""
    meta = ffprobe(video_path)

    court = (
        {"court_detected": False, "homography": None, "court_polygon_px": None, "confidence": 0.0}
        if degraded
        else detect_court(video_path, sample_seconds=min(60.0, meta["duration_s"]))
    )

    person_result = analyze_person_motion(
        video_path,
        court.get("court_polygon_px"),
        hz=ANALYSIS_HZ,
        max_seconds=None,
        degraded=degraded,
    )
    ball_result = (
        {"hz": ANALYSIS_HZ, "per_frame": [], "confidence": 0.0}
        if degraded
        else analyze_ball_motion(video_path, hz=ANALYSIS_HZ, max_seconds=None)
    )

    seg_result = segment_points(person_result, ball_result, degraded=degraded, duration_s=meta["duration_s"])

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
            {"index": i, "clip": {"start_s": s["start_s"], "end_s": s["end_s"]}, "confidence": s["confidence"]}
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
    }
