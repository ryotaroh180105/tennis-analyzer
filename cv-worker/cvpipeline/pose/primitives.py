"""指標計算プリミティブ（12-form-analysis.md §指標エンジン）。

shot-mechanics.v1.yamlのmetrics[].primitiveから呼ばれる純粋関数群。
ロール名（dominant_wrist等）の実ランドマークへの解決もここで行う。
新しい計算方法が必要になった場合のみここにプリミティブを追加する
（YAML宣言で表現できることをここに追加しない。不変原則2）。

z軸の符号規約（要注意・実データでの検証が必要）：MediaPipe world landmarksは
被写体の腰を原点とし、カメラに正対した被写体基準でzは「カメラに近いほど小さい」。
forward_of_body・line_separationはこの規約を前提にしている。斜め後方アングル
（03/12の撮影ガイド）ではカメラ光軸と体の正面が一致しないため、実際の値の
妥当性は実データで検証すること（12 §リスク: モーションブラー・アングル依存の一種）。
"""

import math

_SIMPLE_PARTS = {"shoulder", "elbow", "wrist", "hip", "knee", "ankle"}


def resolve_role(role: str, dominant_side: str, joints: dict) -> dict | None:
    """'dominant_wrist' / 'nondominant_knee' 等のロール名を実ランドマークに解決する。"""
    if role.startswith("dominant_"):
        side, part = dominant_side, role[len("dominant_") :]
    elif role.startswith("nondominant_"):
        side = "left" if dominant_side == "right" else "right"
        part = role[len("nondominant_") :]
    else:
        raise ValueError(f"unsupported joint role: {role}")
    if part not in _SIMPLE_PARTS:
        raise ValueError(f"unsupported joint role: {role}")
    return joints.get(f"{side}_{part}")


def vec(p: dict, q: dict) -> tuple[float, float, float]:
    return (q["x"] - p["x"], q["y"] - p["y"], q["z"] - p["z"])


def angle_deg(a: dict, b: dict, c: dict) -> float:
    """b を頂点とする a-b-c の角度（度）。detectors.pyのフェーズ検出でも使う共有ヘルパー。"""
    ba, bc = vec(b, a), vec(b, c)
    mag_ba = math.sqrt(sum(v * v for v in ba))
    mag_bc = math.sqrt(sum(v * v for v in bc))
    if mag_ba == 0 or mag_bc == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(ba, bc))
    cos_theta = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
    return math.degrees(math.acos(cos_theta))


def dist(p: dict, q: dict) -> float:
    return math.sqrt(sum(v * v for v in vec(p, q)))


def _torso_scale(joints: dict, dominant_side: str) -> float:
    return dist(joints[f"{dominant_side}_shoulder"], joints[f"{dominant_side}_hip"]) or 1.0


def joint_angle(joints: dict, dominant_side: str, args: dict) -> float | None:
    a, b, c = (resolve_role(r, dominant_side, joints) for r in args["points"])
    if a is None or b is None or c is None:
        return None
    return round(angle_deg(a, b, c), 2)


def relative_height(joints: dict, dominant_side: str, args: dict) -> float | None:
    p = resolve_role(args["point"], dominant_side, joints)
    ref = resolve_role(args["ref"], dominant_side, joints)
    if p is None or ref is None:
        return None
    return round(abs(p["y"] - ref["y"]) / _torso_scale(joints, dominant_side), 3)


def forward_of_body(joints: dict, dominant_side: str, args: dict) -> float | None:
    p = resolve_role(args["point"], dominant_side, joints)
    if p is None:
        return None
    hip_mid_z = (joints["left_hip"]["z"] + joints["right_hip"]["z"]) / 2
    return round((hip_mid_z - p["z"]) / _torso_scale(joints, dominant_side), 3)


def _line_yaw_deg(joints: dict, line_name: str) -> float:
    prefix = "shoulder" if line_name == "shoulder_line" else "hip"
    left, right = joints[f"left_{prefix}"], joints[f"right_{prefix}"]
    return math.degrees(math.atan2(right["z"] - left["z"], right["x"] - left["x"]))


def line_separation(joints: dict, dominant_side: str, args: dict) -> float:
    line_a, line_b = args["lines"]
    return round(abs(_line_yaw_deg(joints, line_a) - _line_yaw_deg(joints, line_b)), 2)


def line_separation_signed(joints: dict, dominant_side: str, args: dict) -> float:
    """符号付きの回旋差（line_separationのabs()を取らない版）。

    片手/両手バックハンドの分離角の向き（文献: 片手=positive/両手=negative、
    コンタクト時）のような定性判定（expected_sign）専用。数値レンジ比較には
    line_separation（符号規約が実装依存で不安定なため）を使うこと。
    """
    line_a, line_b = args["lines"]
    return round(_line_yaw_deg(joints, line_a) - _line_yaw_deg(joints, line_b), 2)


def event_interval(frames_by_event: dict, args: dict) -> float | None:
    f0, f1 = frames_by_event.get(args["from_event"]), frames_by_event.get(args["to_event"])
    if f0 is None or f1 is None:
        return None
    return round((f1["t"] - f0["t"]) * 1000, 1)


def angle_delta(frames_by_event: dict, dominant_side: str, args: dict) -> float | None:
    f0, f1 = frames_by_event.get(args["from_event"]), frames_by_event.get(args["to_event"])
    if f0 is None or f1 is None or f0["joints"] is None or f1["joints"] is None:
        return None
    a0 = joint_angle(f0["joints"], dominant_side, {"points": args["points"]})
    a1 = joint_angle(f1["joints"], dominant_side, {"points": args["points"]})
    if a0 is None or a1 is None:
        return None
    return round(abs(a1 - a0), 2)


SINGLE_FRAME_PRIMITIVES = {
    "joint_angle",
    "relative_height",
    "forward_of_body",
    "line_separation",
    "line_separation_signed",
}
EVENT_PAIR_PRIMITIVES = {"event_interval", "angle_delta"}
