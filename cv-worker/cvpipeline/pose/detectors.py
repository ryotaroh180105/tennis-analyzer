"""ショット別フェーズ検出器（12-form-analysis.md §ショット別フェーズモデル）。

各検出器は1スイング分のランドマークウィンドウを受け取り、キーイベント名→フレームの
辞書を返す（材料不足ならNone）。ヒューリスティックであり精度非保証・パイプライン疎通が
目的（stage2/3と同じdev軽量CVの位置づけ）。

detector名（serve_like/groundstroke/volley）は shot-mechanics.v1.yaml の
shots.<shot_type>.detector から参照される。
"""

import math

from cvpipeline.pose.primitives import angle_deg


def dominant_side(landmark_series: list[dict]) -> str:
    """打球腕の側を推定する（動画全体から1回だけ。スイングごとの再判定はしない）。

    ラケット腕は手首の可動レンジが大きい前提のヒューリスティック。
    """
    max_range = {"left": 0.0, "right": 0.0}
    prev = {"left": None, "right": None}
    for frame in landmark_series:
        if frame["joints"] is None:
            continue
        for side in ("left", "right"):
            wrist = frame["joints"][f"{side}_wrist"]
            if prev[side] is not None:
                delta = math.sqrt(sum((wrist[c] - prev[side][c]) ** 2 for c in "xyz"))
                max_range[side] = max(max_range[side], delta)
            prev[side] = wrist
    return "right" if max_range["right"] >= max_range["left"] else "left"


def detect_serve_like(window: list[dict], dominant: str) -> dict | None:
    """serve/smash共通。トス(またはポインティング)頂点→トロフィー→インパクト。"""
    valid = [f for f in window if f["joints"] is not None]
    if len(valid) < 5:
        return None

    non_dominant = "left" if dominant == "right" else "right"

    impact_frame = max(valid, key=lambda f: -f["joints"][f"{dominant}_wrist"]["y"])
    impact_idx = valid.index(impact_frame)

    pre_impact = valid[: impact_idx + 1] or valid[:1]
    toss_apex_frame = max(pre_impact, key=lambda f: -f["joints"][f"{non_dominant}_wrist"]["y"])
    toss_apex_idx = valid.index(toss_apex_frame)

    trophy_window = valid[toss_apex_idx : impact_idx + 1] or [toss_apex_frame]
    trophy_frame = min(
        trophy_window,
        key=lambda f: angle_deg(
            f["joints"][f"{non_dominant}_hip"],
            f["joints"][f"{non_dominant}_knee"],
            f["joints"][f"{non_dominant}_ankle"],
        ),
    )

    return {"toss_apex": toss_apex_frame, "trophy": trophy_frame, "impact": impact_frame}


def detect_groundstroke(window: list[dict], dominant: str) -> dict | None:
    """forehand/backhand。バックスイング最深点→コンタクト（手首速度ピーク）→フォロー終端。"""
    valid = [f for f in window if f["joints"] is not None]
    if len(valid) < 5:
        return None

    speeds = []
    for k in range(1, len(valid)):
        f0, f1 = valid[k - 1], valid[k]
        dt = f1["t"] - f0["t"]
        if dt <= 0:
            continue
        w0, w1 = f0["joints"][f"{dominant}_wrist"], f1["joints"][f"{dominant}_wrist"]
        dist = math.sqrt(sum((w1[c] - w0[c]) ** 2 for c in "xyz"))
        speeds.append((dist / dt, k))
    if not speeds:
        return None
    _, contact_k = max(speeds)
    contact_frame = valid[contact_k]

    def behind_body(f: dict) -> float:
        wrist = f["joints"][f"{dominant}_wrist"]
        hip_mid_z = (f["joints"]["left_hip"]["z"] + f["joints"]["right_hip"]["z"]) / 2
        return wrist["z"] - hip_mid_z  # 大きいほど後方（primitives.pyのz規約を参照）

    pre_contact = valid[: contact_k + 1] or valid[:1]
    backswing_frame = max(pre_contact, key=behind_body)

    follow_frame = valid[-1]
    post_contact = valid[contact_k:]
    for k in range(1, len(post_contact)):
        f0, f1 = post_contact[k - 1], post_contact[k]
        dt = f1["t"] - f0["t"]
        if dt <= 0:
            continue
        w0, w1 = f0["joints"][f"{dominant}_wrist"], f1["joints"][f"{dominant}_wrist"]
        dist = math.sqrt(sum((w1[c] - w0[c]) ** 2 for c in "xyz"))
        if (dist / dt) < 1.0:  # フォロースルー終端の速度低下閾値（placeholder）
            follow_frame = f1
            break

    return {"backswing_end": backswing_frame, "contact": contact_frame, "follow_end": follow_frame}


def detect_volley(window: list[dict], dominant: str) -> dict | None:
    """volley。ボレーはスイングしないため、窓の先頭をpunch開始、体の最前方到達点をcontactとする。"""
    valid = [f for f in window if f["joints"] is not None]
    if len(valid) < 5:
        return None

    def forward(f: dict) -> float:
        wrist = f["joints"][f"{dominant}_wrist"]
        hip_mid_z = (f["joints"]["left_hip"]["z"] + f["joints"]["right_hip"]["z"]) / 2
        return hip_mid_z - wrist["z"]

    contact_frame = max(valid, key=forward)
    return {"punch_start": valid[0], "contact": contact_frame}


DETECTORS = {
    "serve_like": detect_serve_like,
    "groundstroke": detect_groundstroke,
    "volley": detect_volley,
}
