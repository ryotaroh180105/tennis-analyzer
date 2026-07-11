"""shot-mechanics.v1.yaml のロード時スキーマ検証（不変原則1・2）。

実在しないロール名・イベント名・primitive参照や、elite_range/expected_signの
排他違反をロード時に拒否する（taxonomyの「存在しない参照はスキーマ検証で拒否」
と同じ規約、12-form-analysis.md §評価モード）。

metricsがelite_range/expected_signのどちらも持たない場合はエラーにしない
（12 §ロールアウト3d・13 A-3の「測定値のみモード」＝status:measured として
評価器側が扱う。文献未確認の指標を推測レンジで埋めないための正規の状態）。
"""

from cvpipeline.pose import primitives
from cvpipeline.pose.detectors import DETECTORS

# detectorが返すframes_by_eventのキー（各detect_*関数の戻り値の辞書キーと一致させる）。
_DETECTOR_EVENTS = {
    "serve_like": {"toss_apex", "trophy", "impact"},
    "groundstroke": {"backswing_end", "contact", "follow_end"},
    "volley": {"punch_start", "contact"},
}

_LINE_NAMES = {"shoulder_line", "hip_line"}


def _validate_role(role: object, where: str) -> None:
    if not isinstance(role, str) or not primitives.is_valid_role(role):
        raise ValueError(f"{where}: unsupported joint role {role!r}")


def _validate_event(event: object, allowed_events: set[str], where: str) -> None:
    if event not in allowed_events:
        raise ValueError(f"{where}: unknown event {event!r} (detector emits: {sorted(allowed_events)})")


def _validate_lines(lines: object, where: str) -> None:
    if not isinstance(lines, list) or set(lines) != _LINE_NAMES:
        raise ValueError(f"{where}: 'lines' must contain exactly {sorted(_LINE_NAMES)}, got {lines!r}")


def _validate_metric(metric: dict, allowed_events: set[str], where: str) -> None:
    metric_id = metric.get("id", "?")
    where = f"{where}[{metric_id}]"

    primitive_name = metric.get("primitive")
    if primitive_name not in primitives.SINGLE_FRAME_PRIMITIVES | primitives.EVENT_PAIR_PRIMITIVES:
        raise ValueError(f"{where}: unknown primitive {primitive_name!r}")

    args = metric.get("args", {})

    if primitive_name in primitives.SINGLE_FRAME_PRIMITIVES:
        if "at" not in metric:
            raise ValueError(f"{where}: single-frame primitive requires 'at'")
        _validate_event(metric["at"], allowed_events, where)

        if primitive_name == "joint_angle":
            for role in args.get("points", []):
                _validate_role(role, where)
        elif primitive_name == "relative_height":
            _validate_role(args.get("point"), where)
            _validate_role(args.get("ref"), where)
        elif primitive_name == "forward_of_body":
            _validate_role(args.get("point"), where)
        elif primitive_name in ("line_separation", "line_separation_signed"):
            _validate_lines(args.get("lines"), where)
    else:  # EVENT_PAIR_PRIMITIVES
        for key in ("from_event", "to_event"):
            if key not in args:
                raise ValueError(f"{where}: {primitive_name} requires args.{key!r}")
            _validate_event(args[key], allowed_events, where)
        if primitive_name == "angle_delta":
            for role in args.get("points", []):
                _validate_role(role, where)

    has_elite_range = "elite_range" in metric
    has_expected_sign = "expected_sign" in metric
    if has_elite_range and has_expected_sign:
        raise ValueError(f"{where}: elite_range と expected_sign は排他（同時指定不可）")
    if has_elite_range and "tolerance" not in metric:
        raise ValueError(f"{where}: elite_range を持つ指標は tolerance が必須")
    if has_expected_sign and metric["expected_sign"] not in ("positive", "negative"):
        raise ValueError(f"{where}: expected_sign は 'positive'|'negative' のみ許可")

    only_style = metric.get("only_style")
    if only_style is not None and only_style not in ("one_handed", "two_handed"):
        raise ValueError(f"{where}: only_style は 'one_handed'|'two_handed' のみ許可")


def validate_shot_mechanics(config: dict) -> None:
    for key in ("version", "defaults", "swing_detection", "shots"):
        if key not in config:
            raise ValueError(f"shot-mechanics config missing required top-level key: {key!r}")

    for shot_type, shot_config in config["shots"].items():
        detector_name = shot_config.get("detector")
        if detector_name not in DETECTORS:
            raise ValueError(f"shots.{shot_type}: unknown detector {detector_name!r}")
        allowed_events = _DETECTOR_EVENTS[detector_name]
        for metric in shot_config.get("metrics", []):
            _validate_metric(metric, allowed_events, f"shots.{shot_type}.metrics")
