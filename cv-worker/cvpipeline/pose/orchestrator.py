"""1動画分のフォーム解析オーケストレーション（12-form-analysis.md）。

抽出→分割→検出→指標評価→集約の各段を関数境界で分離し、下流（指標定義変更時の
再計算）だけを再実行できるようにする（不変原則3）。
"""

from cvpipeline.config_loader import load_shot_mechanics
from cvpipeline.pose.detectors import DETECTORS, dominant_side as detect_dominant_side
from cvpipeline.pose.landmarks import extract_landmarks
from cvpipeline.pose.metrics_engine import aggregate_metric, evaluate_metric
from cvpipeline.pose.swing_detection import split_swings


def analyze_landmarks(
    landmark_series: list[dict],
    shot_type: str,
    backhand_style: str | None = None,
    config: dict | None = None,
) -> dict:
    """既に抽出済みのランドマーク系列から指標を計算する（指標定義だけの再計算に使う。不変原則3）。"""
    config = config or load_shot_mechanics()
    shot_config = config["shots"][shot_type]
    detector = DETECTORS[shot_config["detector"]]
    min_visibility = config["defaults"]["min_landmark_visibility"]
    max_feedback = config["defaults"]["max_feedback_metrics"]

    dominant = detect_dominant_side(landmark_series)
    windows = split_swings(landmark_series, dominant, config["swing_detection"])

    swings = []
    for window in windows:
        frames_by_event = detector(window, dominant)
        if frames_by_event is None:
            continue
        swing_result = {}
        for metric in shot_config["metrics"]:
            evaluated = evaluate_metric(metric, frames_by_event, dominant, min_visibility, backhand_style)
            if evaluated is not None:
                swing_result[metric["id"]] = evaluated
        swings.append({"t": window[0]["t"], "metrics": swing_result})

    applicable_metrics = [
        m for m in shot_config["metrics"] if not m.get("only_style") or m["only_style"] == backhand_style
    ]

    metrics = []
    for metric in applicable_metrics:
        values = [
            s["metrics"][metric["id"]]["value"]
            for s in swings
            if metric["id"] in s["metrics"] and s["metrics"][metric["id"]]["value"] is not None
        ]
        metrics.append(aggregate_metric(metric, values))

    insufficient_data = len(swings) < config["swing_detection"]["min_valid_swings"]

    feedback_metrics = []
    if not insufficient_data:
        ranked = sorted(
            (m for m in metrics if m["status"] == "out_of_range"),
            key=lambda m: max(m["elite_range"][0] - m["measured"], m["measured"] - m["elite_range"][1], 0.0),
            reverse=True,
        )
        feedback_metrics = [m["id"] for m in ranked[:max_feedback]]

    valid_ratio = (
        sum(1 for f in landmark_series if f["joints"] is not None) / len(landmark_series) if landmark_series else 0.0
    )

    return {
        "shot_type": shot_type,
        "dominant_side": dominant,
        "swing_count": len(swings),
        "insufficient_data": insufficient_data,
        "swings": swings,
        "metrics": metrics,
        "feedback_metrics": feedback_metrics,
        "confidence": {"pose_detection_ratio": round(valid_ratio, 3)},
        "citation_status": config["citation_status"],
    }


def analyze_form(
    video_path: str,
    model_path: str,
    shot_type: str,
    backhand_style: str | None = None,
    hz: float = 30.0,
    max_seconds: float | None = None,
) -> dict:
    """動画1本分のオーケストレーション。ランドマーク抽出＋analyze_landmarksの実行。

    戻り値には "landmark_series" も含む（呼び出し側がS3に保存し中間出力として残す。不変原則3）。
    """
    config = load_shot_mechanics()
    landmark_series = extract_landmarks(video_path, model_path, hz=hz, max_seconds=max_seconds)
    result = analyze_landmarks(landmark_series, shot_type, backhand_style, config)
    result["landmark_series"] = landmark_series
    return result
