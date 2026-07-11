"""ステージ6: サーブ骨格解析（Phase 3。01 §Phase3 / 06-pro-reference-data.md）。

MediaPipe Pose Landmarker（Tasks API、Apache-2.0・事前学習済みモデル）で骨格系列を抽出する。
RT-DETR/TrackNet系と違い学習データ調達がボトルネックにならないため、他ステージの
「dev軽量代替CV」とは異なり実モデルをそのまま使う（05-tech-stack.md §CV）。

フェーズ分割（構え/トス/トロフィー/加速/インパクト/フォロー）は手首の垂直方向の
速度・高さから検出する古典的ヒューリスティックであり、他ステージと同様
精度非保証・パイプライン疎通が目的（10 §CVパイプライン実装指針と同じ位置づけ）。

角度・タイミング指標はカメラ距離・体格に不変な正規化値のみ算出する
（06 §比較アルゴリズム3: 角度・肩腰基準の相対距離・タイミング比）。
ランドマークのvisibilityが低い区間は該当指標を unknown として返す
（CLAUDE.md 不変原則1: 誤った断定より未分類を優先）。
"""

import math

# 解析に使う12関節のみ（33点全ては保持しない。JSONB payloadを軽量に保つ）
_JOINT_LANDMARKS = {
    "left_shoulder": "LEFT_SHOULDER",
    "right_shoulder": "RIGHT_SHOULDER",
    "left_elbow": "LEFT_ELBOW",
    "right_elbow": "RIGHT_ELBOW",
    "left_wrist": "LEFT_WRIST",
    "right_wrist": "RIGHT_WRIST",
    "left_hip": "LEFT_HIP",
    "right_hip": "RIGHT_HIP",
    "left_knee": "LEFT_KNEE",
    "right_knee": "RIGHT_KNEE",
    "left_ankle": "LEFT_ANKLE",
    "right_ankle": "RIGHT_ANKLE",
}


def extract_landmarks(video_path: str, model_path: str, hz: float, max_seconds: float | None = None) -> list[dict]:
    """MediaPipe Pose Landmarker（VIDEO mode）でフレームごとの骨格ワールド座標を抽出する。

    pose_world_landmarks（メートル単位・腰基準）を使う。pose_landmarks（画像正規化座標）は
    カメラ距離に依存するため角度・比率算出には使わない（06 §正規化指標）。
    """
    import cv2
    import mediapipe as mp

    from cvpipeline.video_io import sample_frames

    base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    series: list[dict] = []
    with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
        for t, frame in sample_frames(video_path, hz=hz, max_seconds=max_seconds):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect_for_video(image, int(t * 1000))

            if not result.pose_world_landmarks:
                series.append({"t": round(t, 3), "joints": None, "visible_ratio": 0.0})
                continue

            world = result.pose_world_landmarks[0]
            joints = {}
            visibilities = []
            for name, landmark_attr in _JOINT_LANDMARKS.items():
                idx = mp.tasks.vision.PoseLandmark[landmark_attr].value
                lm = world[idx]
                joints[name] = {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
                visibilities.append(lm.visibility)

            series.append(
                {
                    "t": round(t, 3),
                    "joints": joints,
                    "visible_ratio": round(sum(visibilities) / len(visibilities), 3) if visibilities else 0.0,
                }
            )

    return series


def _vec(p: dict, q: dict) -> tuple[float, float, float]:
    return (q["x"] - p["x"], q["y"] - p["y"], q["z"] - p["z"])


def _angle_deg(a: dict, b: dict, c: dict) -> float:
    """b を頂点とする a-b-c の角度（度）。3D world座標のベクトル内積から算出。"""
    ba = _vec(b, a)
    bc = _vec(b, c)
    mag_ba = math.sqrt(sum(v * v for v in ba))
    mag_bc = math.sqrt(sum(v * v for v in bc))
    if mag_ba == 0 or mag_bc == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(ba, bc))
    cos_theta = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
    return math.degrees(math.acos(cos_theta))


def _dist(p: dict, q: dict) -> float:
    return math.sqrt(sum(v * v for v in _vec(p, q)))


def _dominant_side(landmark_series: list[dict]) -> str:
    """打球腕の側を推定する。ラケット腕は接触時にトス腕より大きく・速く動く前提のヒューリスティック。"""
    max_range = {"left": 0.0, "right": 0.0}
    prev = {"left": None, "right": None}
    for frame in landmark_series:
        if frame["joints"] is None:
            continue
        for side in ("left", "right"):
            wrist = frame["joints"][f"{side}_wrist"]
            if prev[side] is not None:
                delta = abs(wrist["y"] - prev[side]["y"])
                max_range[side] = max(max_range[side], delta)
            prev[side] = wrist
    return "right" if max_range["right"] >= max_range["left"] else "left"


def segment_phases(landmark_series: list[dict]) -> dict:
    """構え/トス/トロフィー/加速/インパクト/フォローのフレーム区間を検出する（ヒューリスティック）。

    材料（有効フレーム）が無い場合は空dictを返す（不変原則1）。
    """
    valid = [f for f in landmark_series if f["joints"] is not None]
    if len(valid) < 5:
        return {}

    dominant = _dominant_side(landmark_series)
    non_dominant = "left" if dominant == "right" else "right"

    # インパクト = ラケット腕手首の世界座標高さ（-y、MediaPipeはy下向きなので符号反転）が最大の瞬間
    impact_frame = max(valid, key=lambda f: -f["joints"][f"{dominant}_wrist"]["y"])
    impact_idx = valid.index(impact_frame)

    # トス頂点 = インパクトより前で、非利き手手首の高さが最大の瞬間
    pre_impact = valid[: impact_idx + 1] or valid[:1]
    toss_apex_frame = max(pre_impact, key=lambda f: -f["joints"][f"{non_dominant}_wrist"]["y"])
    toss_apex_idx = valid.index(toss_apex_frame)

    # トロフィー = トス頂点〜インパクトの間で、軸足（利き手と反対側の脚）の膝が最も曲がった瞬間
    window = valid[toss_apex_idx : impact_idx + 1] or [toss_apex_frame]
    trophy_frame = min(
        window,
        key=lambda f: _angle_deg(
            f["joints"][f"{non_dominant}_hip"], f["joints"][f"{non_dominant}_knee"], f["joints"][f"{non_dominant}_ankle"]
        ),
    )

    t0, t_last = valid[0]["t"], valid[-1]["t"]
    return {
        "dominant_side": dominant,
        "preparation": {"start_s": t0, "end_s": toss_apex_frame["t"]},
        "toss": {"start_s": t0, "end_s": toss_apex_frame["t"]},
        "trophy": {"start_s": trophy_frame["t"], "end_s": trophy_frame["t"]},
        "acceleration": {"start_s": trophy_frame["t"], "end_s": impact_frame["t"]},
        "impact": {"start_s": impact_frame["t"], "end_s": impact_frame["t"]},
        "follow_through": {"start_s": impact_frame["t"], "end_s": t_last},
        "_frames": {"toss_apex": toss_apex_frame, "trophy": trophy_frame, "impact": impact_frame},
    }


def _metric_confidence(frame: dict, min_visibility: float) -> float:
    return frame["visible_ratio"] if frame["visible_ratio"] >= min_visibility else 0.0


def compute_metrics(landmark_series: list[dict], phases: dict, config: dict) -> list[dict]:
    """serve-mechanics.v1.yaml の各指標を算出し、elite_rangeとの比較結果を返す。"""
    if not phases:
        return []

    min_visibility = config["min_landmark_visibility"]
    frames = phases["_frames"]
    dominant = phases["dominant_side"]
    non_dominant = "left" if dominant == "right" else "right"

    results = []
    for metric in config["metrics"]:
        value = None
        confidence = 0.0

        if metric["id"] == "knee_flexion_at_trophy":
            f = frames["trophy"]
            confidence = _metric_confidence(f, min_visibility)
            if confidence:
                j = f["joints"]
                value = _angle_deg(j[f"{non_dominant}_hip"], j[f"{non_dominant}_knee"], j[f"{non_dominant}_ankle"])

        elif metric["id"] == "elbow_height_at_trophy":
            f = frames["trophy"]
            confidence = _metric_confidence(f, min_visibility)
            if confidence:
                j = f["joints"]
                scale = _dist(j[f"{dominant}_shoulder"], j[f"{dominant}_hip"]) or 1.0
                value = abs(j[f"{dominant}_elbow"]["y"] - j[f"{dominant}_shoulder"]["y"]) / scale

        elif metric["id"] == "shoulder_hip_separation_at_trophy":
            f = frames["trophy"]
            confidence = _metric_confidence(f, min_visibility)
            if confidence:
                j = f["joints"]
                shoulder_yaw = math.degrees(
                    math.atan2(
                        j["right_shoulder"]["z"] - j["left_shoulder"]["z"],
                        j["right_shoulder"]["x"] - j["left_shoulder"]["x"],
                    )
                )
                hip_yaw = math.degrees(
                    math.atan2(j["right_hip"]["z"] - j["left_hip"]["z"], j["right_hip"]["x"] - j["left_hip"]["x"])
                )
                value = abs(shoulder_yaw - hip_yaw)

        elif metric["id"] == "elbow_extension_at_impact":
            f = frames["impact"]
            confidence = _metric_confidence(f, min_visibility)
            if confidence:
                j = f["joints"]
                value = _angle_deg(j[f"{dominant}_shoulder"], j[f"{dominant}_elbow"], j[f"{dominant}_wrist"])

        elif metric["id"] == "contact_height_relative":
            f = frames["impact"]
            confidence = _metric_confidence(f, min_visibility)
            if confidence:
                j = f["joints"]
                scale = _dist(j[f"{dominant}_shoulder"], j[f"{dominant}_hip"]) or 1.0
                value = (j[f"{dominant}_shoulder"]["y"] - j[f"{dominant}_wrist"]["y"]) / scale

        elif metric["id"] == "toss_apex_to_impact_ms":
            toss_f, impact_f = frames["toss_apex"], frames["impact"]
            confidence = min(_metric_confidence(toss_f, min_visibility), _metric_confidence(impact_f, min_visibility))
            if confidence:
                value = (impact_f["t"] - toss_f["t"]) * 1000

        results.append(_evaluate_metric(metric, value, confidence))

    return results


def _evaluate_metric(metric: dict, value: float | None, confidence: float) -> dict:
    if value is None or confidence <= 0:
        return {
            "id": metric["id"],
            "phase": metric["phase"],
            "unit": metric["unit"],
            "measured": None,
            "elite_range": metric["elite_range"],
            "status": "unknown",
            "confidence": 0.0,
            "advice_key": metric["advice_key"],
        }

    lo, hi = metric["elite_range"]
    tolerance = metric["tolerance"]
    if lo <= value <= hi:
        status = "in_range"
    elif (lo - tolerance) <= value <= (hi + tolerance):
        status = "borderline"
    else:
        status = "out_of_range"

    return {
        "id": metric["id"],
        "phase": metric["phase"],
        "unit": metric["unit"],
        "measured": round(value, 2),
        "elite_range": metric["elite_range"],
        "status": status,
        "confidence": confidence,
        "advice_key": metric["advice_key"],
    }


def rank_feedback_metrics(metrics: list[dict], max_metrics: int) -> list[dict]:
    """レンジ逸脱の大きい順に上位N件だけを返す（06 §比較アルゴリズム4: 全部指摘しない）。"""

    def _deviation(m: dict) -> float:
        if m["status"] in ("in_range", "unknown") or m["measured"] is None:
            return 0.0
        lo, hi = m["elite_range"]
        return max(lo - m["measured"], m["measured"] - hi, 0.0)

    ranked = sorted((m for m in metrics if m["status"] == "out_of_range"), key=_deviation, reverse=True)
    return ranked[:max_metrics]


def analyze_serve(video_path: str, model_path: str, hz: float = 30.0, max_seconds: float | None = None) -> dict:
    """サーブ動画1本分のオーケストレーション（precheck相当。degradedモードは無し＝
    骨格が取れなければ全指標がunknownになるだけで、パイプライン自体は失敗させない）。
    """
    from cvpipeline.config_loader import load_serve_mechanics

    config = load_serve_mechanics()
    landmark_series = extract_landmarks(video_path, model_path, hz=hz, max_seconds=max_seconds)
    phases = segment_phases(landmark_series)
    metrics = compute_metrics(landmark_series, phases, config)
    feedback = rank_feedback_metrics(metrics, config["max_feedback_metrics"])

    valid_ratio = (
        sum(1 for f in landmark_series if f["joints"] is not None) / len(landmark_series) if landmark_series else 0.0
    )

    return {
        "phases": {k: v for k, v in phases.items() if k != "_frames"},
        "metrics": metrics,
        "feedback_metrics": [m["id"] for m in feedback],
        "confidence": {"pose_detection_ratio": round(valid_ratio, 3)},
        "citation_status": config["citation_status"],
    }
