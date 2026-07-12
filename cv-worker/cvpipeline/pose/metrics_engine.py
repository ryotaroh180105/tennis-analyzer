"""shot-mechanics.v1.yamlの指標定義をスイング単位で評価し、セッション単位に集約する
（12-form-analysis.md §指標エンジン／集約は中央値+IQR）。
"""

from cvpipeline.pose import primitives


def evaluate_metric(metric: dict, frames_by_event: dict, dominant_side: str, min_visibility: float, backhand_style: str | None) -> dict | None:
    """1スイング分の指標を評価する。only_styleに合致しなければNone（このスイングの対象外）。"""
    if metric.get("only_style") and metric["only_style"] != backhand_style:
        return None

    primitive_name = metric["primitive"]
    value = None
    confidence = 0.0

    if primitive_name in primitives.SINGLE_FRAME_PRIMITIVES:
        frame = frames_by_event.get(metric["at"])
        if frame is not None and frame["joints"] is not None and frame["visible_ratio"] >= min_visibility:
            confidence = frame["visible_ratio"]
            value = getattr(primitives, primitive_name)(frame["joints"], dominant_side, metric["args"])
    elif primitive_name in primitives.EVENT_PAIR_PRIMITIVES:
        f0 = frames_by_event.get(metric["args"]["from_event"])
        f1 = frames_by_event.get(metric["args"]["to_event"])
        if f0 is not None and f1 is not None:
            # event_intervalはタイミングのみでjoints不要（visibilityゲートも適用しない）。
            # angle_deltaは角度算出にjointsを使うためvisibilityゲートを適用する。
            if primitive_name == "event_interval":
                confidence = 1.0
                value = primitives.event_interval(frames_by_event, metric["args"])
            elif (
                f0["joints"] is not None
                and f1["joints"] is not None
                and min(f0["visible_ratio"], f1["visible_ratio"]) >= min_visibility
            ):
                confidence = min(f0["visible_ratio"], f1["visible_ratio"])
                value = primitives.angle_delta(frames_by_event, dominant_side, metric["args"])
    else:
        raise ValueError(f"unsupported primitive: {primitive_name}")

    return {"id": metric["id"], "value": value, "confidence": confidence if value is not None else 0.0}


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _iqr(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    s = sorted(values)
    n = len(s)

    def _q(p: float) -> float:
        idx = p * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        frac = idx - lo
        return s[lo] + (s[hi] - s[lo]) * frac

    return _q(0.75) - _q(0.25)


def evaluate_status(value: float, elite_range: list[float], tolerance: float) -> str:
    lo, hi = elite_range
    if lo <= value <= hi:
        return "in_range"
    if (lo - tolerance) <= value <= (hi + tolerance):
        return "borderline"
    return "out_of_range"


def evaluate_qualitative_status(value: float, expected_sign: str) -> str:
    """数値レンジではなく符号（向き）のみで判定する定性指標用（不変原則1: 精緻な数値の裏付けが
    ない場合でも、方向性のみ文献で裏付けられていれば「unknown」より評価を優先する）。
    """
    if value == 0:
        return "out_of_range"
    actual_sign = "positive" if value > 0 else "negative"
    return "in_range" if actual_sign == expected_sign else "out_of_range"


def aggregate_metric(metric: dict, per_swing_values: list[float]) -> dict:
    """1指標について有効スイング全体の中央値・IQR・ばらつき判定・レンジ比較をまとめる。

    3つの評価モード（elite_range/expected_signの併存は無い前提。ロード時検証で排他を担保）：
      - 定量（elite_range + tolerance）: 中央値がレンジ内かで in_range/borderline/out_of_range
      - 定性（expected_sign）: 中央値の符号一致で in_range/out_of_range
      - 測定値のみ（どちらも無し）: レンジ比較をせず status="measured"。文献未確認の指標に
        推測レンジを割り当てないための状態（13 A-3、12 §ロールアウト3d）。注目ポイント
        （feedback_metrics）はstatus=="out_of_range"のみを対象にするため、measuredの
        指標は自動的にコーチング対象から外れる。
    """
    has_elite_range = "elite_range" in metric
    has_expected_sign = "expected_sign" in metric

    base = {
        "id": metric["id"],
        "phase": metric["at"],
        "unit": metric["unit"],
        "elite_range": metric["elite_range"] if has_elite_range else None,
        "expected_sign": metric.get("expected_sign"),
        "advice_key": metric["advice_key"],
    }

    if not per_swing_values:
        return {**base, "measured": None, "iqr": None, "status": "unknown", "high_variance": False, "valid_swings": 0}

    median = _median(per_swing_values)
    iqr = _iqr(per_swing_values)

    cv_max = metric.get("consistency_cv_max")
    high_variance = bool(cv_max is not None and median != 0 and (iqr / abs(median)) > cv_max)

    if has_elite_range:
        status = evaluate_status(median, metric["elite_range"], metric["tolerance"])
    elif has_expected_sign:
        status = evaluate_qualitative_status(median, metric["expected_sign"])
        signs = {"positive" if v > 0 else "negative" if v < 0 else "zero" for v in per_swing_values}
        high_variance = high_variance or len(signs) > 1
    else:
        status = "measured"

    return {
        **base,
        "measured": round(median, 2),
        "iqr": round(iqr, 2),
        "status": status,
        "high_variance": high_variance,
        "valid_swings": len(per_swing_values),
    }
