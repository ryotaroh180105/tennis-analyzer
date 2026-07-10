"""ステージ5: ショット分割・粗いショット種別/終端イベント推定（01 §Phase1）。

TrackNet等の実弾道追跡・実際のショット分類モデルは未導入のため、stage3の
ball_motion（打点候補のピーク検出のみ）を使った古典的CV代替にとどめる。
shot_type/terminalは信頼できる根拠が無いため、原則 confidence を低く申告し、
taxonomy.v1.yaml側のmin_confidenceゲートで unknown に落とすことを前提とする
（不変原則1：誤った断定より未分類を優先）。唯一 confidence 1.0 で断定するのは
「各ポイントの最初のショットはサーブである」というルール上自明な事実のみ。
"""

from cvpipeline.config_loader import load_segmentation_params


def _detect_shot_times(ball_frames: list[dict], start_s: float, end_s: float, threshold: float, min_interval_s: float) -> list[float]:
    in_point = [f for f in ball_frames if start_s <= f["t"] <= end_s]
    shots: list[float] = []
    last_t: float | None = None
    above = False
    for f in in_point:
        t, value = f["t"], f["ball_motion"]
        if value >= threshold and not above:
            if last_t is None or t - last_t >= min_interval_s:
                shots.append(t)
                last_t = t
            above = True
        elif value < threshold:
            above = False
    return shots


def detect_shots(points: list[dict], ball_result: dict, degraded: bool) -> list[dict]:
    """points: [{"start_s","end_s"}, ...]（stage4の出力）。戻り値は points と同じ長さのショット配列のリスト。"""
    params = load_segmentation_params()["shots"]

    if degraded or not ball_result.get("per_frame"):
        # 縮退モードはball_motionが無いためショット分割自体を行わない（0件・全体unknown）
        return [[] for _ in points]

    all_shots: list[list[dict]] = []
    for point in points:
        shot_times = _detect_shot_times(
            ball_result["per_frame"],
            point["start_s"],
            point["end_s"],
            params["ball_motion_threshold"],
            params["min_interval_s"],
        )
        shots = []
        for i, t in enumerate(shot_times):
            is_serve = i == 0
            is_last = i == len(shot_times) - 1
            shot = {
                "index": i,
                "t": round(t, 2),
                "interval_s": round(t - shot_times[i - 1], 2) if i > 0 else None,
                "type": "serve" if is_serve else "unknown",
                "type_confidence": 1.0 if is_serve else 0.0,
            }
            if is_last:
                # ラリー終端の勝敗種別（net/out/winner）は実弾道追跡なしには判定不能。
                # 常にunknown相当の低confidenceを申告し、taxonomy側のゲートに委ねる。
                shot["terminal"] = {"type": "unknown", "confidence": 0.2}
            shots.append(shot)
        all_shots.append(shots)

    return all_shots
