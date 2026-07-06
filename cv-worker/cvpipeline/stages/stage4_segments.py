"""ステージ4: ポイント区間分割（ルールベース＋ヒステリシス。config/segmentation.v1.yaml準拠）。

合成活動量 = w_person*person_motion + w_ball*ball_motion をヒステリシスで2値化し、
プレー区間を検出する。バッファ・結合・最小長のルールもYAMLから読む
（不変原則2：しきい値のコード内定数を禁止）。
"""

from cvpipeline.config_loader import load_segmentation_params


def _combined_series(person_frames: list[dict], ball_frames: list[dict], weights: dict) -> list[dict]:
    ball_by_t = {f["t"]: f["ball_motion"] for f in ball_frames}
    combined = []
    for pf in person_frames:
        t = pf["t"]
        ball_motion = ball_by_t.get(t, 0.0)
        value = weights["w_person"] * pf["person_motion"] + weights["w_ball"] * ball_motion
        combined.append({"t": t, "value": value})
    return combined


def _smooth(series: list[dict], window_s: float) -> list[dict]:
    if not series or window_s <= 0:
        return series
    smoothed = []
    for i, point in enumerate(series):
        t0 = point["t"] - window_s / 2
        t1 = point["t"] + window_s / 2
        window_vals = [p["value"] for p in series if t0 <= p["t"] <= t1]
        smoothed.append({"t": point["t"], "value": sum(window_vals) / len(window_vals)})
    return smoothed


def segment_points(
    person_result: dict, ball_result: dict, degraded: bool, duration_s: float | None = None
) -> dict:
    params = load_segmentation_params()
    activity = params["degraded"] if degraded else params["activity"]
    buffers = params["buffers"]
    merge = params["merge"]

    weights = {"w_person": activity["w_person"], "w_ball": activity["w_ball"]}
    combined = _combined_series(person_result["per_frame"], ball_result["per_frame"], weights)
    combined = _smooth(combined, activity.get("smoothing_window_s", 0))

    on_threshold = activity["on_threshold"]
    off_threshold = activity["off_threshold"]
    min_play_s = activity.get("min_play_s", 0)
    min_dead_s = activity.get("min_dead_s", 0)

    raw_segments: list[tuple[float, float]] = []
    in_play = False
    start_t = 0.0
    last_t = 0.0

    for point in combined:
        t, value = point["t"], point["value"]
        last_t = t
        if not in_play and value >= on_threshold:
            in_play = True
            start_t = t
        elif in_play and value < off_threshold:
            in_play = False
            if t - start_t >= min_play_s:
                raw_segments.append((start_t, t))

    if in_play and last_t - start_t >= min_play_s:
        raw_segments.append((start_t, last_t))

    # 短いデッドタイムで挟まれた区間は結合する
    merged: list[list[float]] = []
    for seg in raw_segments:
        if merged and seg[0] - merged[-1][1] < min_dead_s:
            merged[-1][1] = seg[1]
        else:
            merged.append(list(seg))

    # バッファを付けて外側に広げる（プレー区間を削らない方向。02）。
    # end_sは動画長でクランプする（実機検証で判明：クランプ無しだと動画長超過の
    # 区間がedit/ffmpegに渡り、-toが範囲外を指定してしまう）。
    buffered = []
    for start, end in merged:
        end_s = end + buffers["post_s"]
        if duration_s is not None:
            end_s = min(end_s, duration_s)
        buffered.append(
            {
                "start_s": max(0.0, start - buffers["pre_s"]),
                "end_s": end_s,
                "confidence": 0.6 if degraded else 0.8,
            }
        )

    # min_gap_s未満の間隔はさらに結合（クリップ重複防止。10）
    final: list[dict] = []
    for seg in buffered:
        if final and seg["start_s"] - final[-1]["end_s"] < merge["min_gap_s"]:
            final[-1]["end_s"] = seg["end_s"]
        else:
            final.append(seg)

    return {"segments": final, "params_version": "segmentation.v1"}
