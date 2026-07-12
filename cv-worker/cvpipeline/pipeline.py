"""stage1-5を統括し、event_streams payload と初期segmentsを組み立てる（analyzeジョブの中身）。

不変原則3（ステージ独立・中間出力保存で下流のみ再実行可能に保つ）に沿って、重い部分
（stage1-3: コート検出・選手・ボール追跡）と軽い部分（stage4-5: 区間分割・ショット検出＋
payload組み立て）を分離する。extract_stage_results() の戻り値はJSON化してR2に保存すれば、
segmentation.v1.yaml変更時などにanalyze_from_stage_results()だけを再実行でき、
30分ジョブの頭（動画再ダウンロード・骨格/コート再検出）からやり直さずに済む（10 §運用）。
"""

import time

from cvpipeline.stages.stage1_court import detect_court
from cvpipeline.stages.stage2_players import analyze_person_motion
from cvpipeline.stages.stage3_ball import analyze_ball_motion
from cvpipeline.stages.stage4_segments import segment_points
from cvpipeline.stages.stage5_shots import detect_shots
from cvpipeline.video_io import ffprobe

ANALYSIS_HZ = 5  # config/segmentation.v1.yaml sampling.base_hz と一致させる


def extract_stage_results(video_path: str, degraded: bool) -> dict:
    """stage1-3（コート検出・選手・ボール追跡）を実行する重い部分。

    戻り値はJSON serializable（R2への永続化・stage_cli.pyのstage_input.jsonとしての
    再利用を前提とする）。analyze_from_stage_results() にそのまま渡せば下流のみ再実行できる。
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

    return {
        "meta": meta,
        "court": court,
        "person_result": person_result,
        "ball_result": ball_result,
        "degraded": degraded,
        "stage_seconds": stage_seconds,
    }


def analyze_from_stage_results(stage_results: dict) -> dict:
    """stage4-5（区間分割・ショット検出）とevent_stream_payload組み立て。軽量・再実行可能。

    戻り値: {"event_stream_payload": {...}, "segments": [{"start_s","end_s","confidence"}],
    "stage_seconds": {"stage1_s"..."stage5_s"}}
    """
    meta = stage_results["meta"]
    court = stage_results["court"]
    person_result = stage_results["person_result"]
    ball_result = stage_results["ball_result"]
    degraded = stage_results["degraded"]
    stage_seconds = dict(stage_results["stage_seconds"])

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


def run_analyze(video_path: str, degraded: bool) -> dict:
    """stage1-5を通しで実行する一括版（既存呼び出し元・ゴールデン回帰との後方互換用）。

    ステージ単位の再開が必要な場合は extract_stage_results() / analyze_from_stage_results()
    を個別に呼ぶこと（不変原則3）。
    """
    stage_results = extract_stage_results(video_path, degraded)
    return analyze_from_stage_results(stage_results)
