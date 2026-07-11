"""ミス分類ルールエンジン（config/taxonomy.v1.yaml準拠）。

when式はPythonのevalを使わず、ASTを許可ノードのみに制限したサンドボックス評価器で
実行する（CLAUDE.md 不変原則2: eval禁止）。存在しないフィールドへの参照は例外を
投げず「比較不成立（False）」に倒す（不変原則1: 誤った断定より未分類を優先）。

shot_type/outcomeの2軸だけは、CVイベントストリームの実データ形状
（cv-worker/cvpipeline/stages/stage5_shots.py が生成するshot/terminal構造）に
直結しているためコードで解決する。それ以外（pressureの判定式・ラベルのmatch・
タグのwhen・しきい値）はすべてtaxonomy.v1.yamlから読む。
"""

import ast
import operator
import os
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/app/config"))


@lru_cache
def load_taxonomy(version: str = "v1") -> dict:
    path = CONFIG_DIR / f"taxonomy.{version}.yaml"
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    _validate_taxonomy(config)
    return config


# ---------------------------------------------------------------
# ロード時スキーマ検証（不変原則1・2: 実在しない参照を実行時まで気付けないのを防ぐ）
# ---------------------------------------------------------------

# when式が参照できるフィールド。thresholds は値をNoneにして「taxonomy["thresholds"]に
# 実在するキーか」を動的にチェックする（キー集合を静的に固定しない）。
_PRESSURE_RULE_ALLOWED_FIELDS: dict[str, set[str] | None] = {
    "prev_opponent_shot": {"landing_depth", "interval_s"},
    "shot": {"type", "landing_depth"},
    "thresholds": None,
}
_SHOT_TAG_ALLOWED_FIELDS: dict[str, set[str] | None] = {
    "shot": {"landing_depth", "type"},
    "thresholds": None,
}
_POINT_TAG_ALLOWED_FIELDS: dict[str, set[str] | None] = {
    "point": {"shot_count"},
    "thresholds": None,
}


def _dotted_path(node: ast.expr) -> tuple[str, ...] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.insert(0, node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.insert(0, node.id)
        return tuple(parts)
    return None


def _iter_operand_nodes(node: ast.AST):
    """when式のグラマー上、識別子が出現しうる位置だけを辿る（Compareの左右・BoolOpの被演算子）。"""
    if isinstance(node, ast.Expression):
        yield from _iter_operand_nodes(node.body)
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from _iter_operand_nodes(value)
    elif isinstance(node, ast.Compare):
        yield node.left
        yield node.comparators[0]
    elif isinstance(node, (ast.Name, ast.Attribute)):
        yield node


def _validate_field_paths(expr: str, allowed: dict[str, set[str] | None], thresholds: dict, where: str) -> None:
    if expr.strip() == "default":
        return
    tree = ast.parse(expr.strip(), mode="eval")
    for operand in _iter_operand_nodes(tree):
        path = _dotted_path(operand)
        if path is None:
            continue
        root = path[0]
        if root not in allowed:
            raise ValueError(f"{where}: unknown field root {root!r} in when expression {expr!r}")
        if root == "thresholds":
            if len(path) != 2 or path[1] not in thresholds:
                raise ValueError(f"{where}: unknown thresholds key in when expression {expr!r}")
            continue
        allowed_attrs = allowed[root]
        if allowed_attrs is not None and (len(path) != 2 or path[1] not in allowed_attrs):
            raise ValueError(f"{where}: unknown field {'.'.join(path)!r} in when expression {expr!r}")


def _validate_taxonomy(config: dict) -> None:
    for key in ("dimensions", "thresholds", "labels"):
        if key not in config:
            raise ValueError(f"taxonomy config missing required top-level key: {key!r}")

    thresholds = config["thresholds"]
    dim_ids: set[str] = set()
    dim_values: dict[str, set[str]] = {}

    for dim in config["dimensions"]:
        did = dim["id"]
        dim_ids.add(did)
        values = set(dim.get("values", []))
        dim_values[did] = values

        for locale, mapping in dim.get("labels", {}).items():
            missing = values - set(mapping.keys())
            if missing:
                raise ValueError(f"dimensions.{did}.labels[{locale}] missing keys for values: {sorted(missing)}")

        if dim.get("source") == "rule":
            rules = dim.get("rules", [])
            if not rules or rules[-1].get("when") != "default":
                raise ValueError(f"dimensions.{did}.rules must end with a default rule (when: default)")
            for rule in rules:
                _validate_field_paths(
                    rule["when"], _PRESSURE_RULE_ALLOWED_FIELDS, thresholds, f"dimensions.{did}.rules"
                )
                if rule["value"] not in values and rule["when"] != "default":
                    raise ValueError(f"dimensions.{did}.rules: rule value {rule['value']!r} not in declared values")

    if not any(entry.get("match", {}) == {} for entry in config["labels"]):
        raise ValueError("taxonomy config must declare a catch-all label (match: {})")

    for entry in config["labels"]:
        for key, val in entry.get("match", {}).items():
            if key not in dim_ids:
                raise ValueError(f"labels: match references unknown dimension {key!r}")
            match_values = val if isinstance(val, list) else [val]
            unknown = set(match_values) - dim_values[key]
            if unknown:
                raise ValueError(f"labels: match for {key!r} has unknown values: {sorted(unknown)}")

    for tag in config.get("tags", []):
        allowed = _POINT_TAG_ALLOWED_FIELDS if tag.get("scope") == "point" else _SHOT_TAG_ALLOWED_FIELDS
        _validate_field_paths(tag["when"], allowed, thresholds, f"tags.{tag['id']}")


# ---------------------------------------------------------------
# サンドボックス評価器
# ---------------------------------------------------------------

_COMPARE_OPS = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Compare,
    ast.Name,
    ast.Attribute,
    ast.Load,
    ast.Constant,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Eq,
    ast.NotEq,
)


class _Unresolved:
    """イベントストリームに実在しないフィールドへの参照を表すセンチネル。"""

    def __repr__(self) -> str:
        return "<unresolved>"


_UNRESOLVED = _Unresolved()


def _resolve_path(node: ast.expr, context: dict):
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.insert(0, node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        raise ValueError("unsupported expression: expected dotted field access")
    parts.insert(0, node.id)

    value = context
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            return _UNRESOLVED
        value = value[part]
    return value


def _eval_node(node: ast.AST, context: dict):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, context)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Name, ast.Attribute)):
        return _resolve_path(node, context)
    if isinstance(node, ast.BoolOp):
        values = [_eval_node(v, context) for v in node.values]
        resolved = [v for v in values if v is not _UNRESOLVED]
        if isinstance(node.op, ast.And):
            return len(resolved) == len(values) and all(bool(v) for v in resolved)
        if isinstance(node.op, ast.Or):
            return any(bool(v) for v in resolved)
        raise ValueError("unsupported boolean operator")
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("chained comparisons are not supported")
        left = _eval_node(node.left, context)
        right = _eval_node(node.comparators[0], context)
        if left is _UNRESOLVED or right is _UNRESOLVED:
            return False
        op = _COMPARE_OPS.get(type(node.ops[0]))
        if op is None:
            raise ValueError("unsupported comparison operator")
        try:
            return op(left, right)
        except TypeError:
            return False
    raise ValueError(f"unsupported expression node: {type(node).__name__}")


def evaluate_when(expr: str, context: dict) -> bool:
    expr = expr.strip()
    if expr == "default":
        return True
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"disallowed expression node in taxonomy rule: {type(node).__name__}")
    return bool(_eval_node(tree, context))


# ---------------------------------------------------------------
# 分類本体
# ---------------------------------------------------------------


def _gated(value: str | None, confidence: float, min_confidence: float | None) -> tuple[str, float]:
    if value is None:
        return "unknown", 0.0
    if min_confidence is not None and confidence < min_confidence:
        return "unknown", confidence
    return value, confidence


def _resolve_pressure(taxonomy: dict, context: dict) -> str:
    dimension = next(d for d in taxonomy["dimensions"] if d["id"] == "pressure")
    for rule in dimension["rules"]:
        if evaluate_when(rule["when"], context):
            return rule["value"]
    return "unforced"  # dimensionにdefaultルールが無い異常系のフォールバック


def _match_label(taxonomy: dict, values: dict[str, str]) -> dict:
    for entry in taxonomy["labels"]:
        match = entry.get("match", {})
        if all(values.get(key) in ((v if isinstance(v, list) else [v])) for key, v in match.items()):
            return entry
    raise ValueError("taxonomy.v1.yaml must have a catch-all label (match: {})")


def classify_point(point: dict, taxonomy: dict) -> dict:
    """1ポイント分のショット列を分類する。戻り値はshotごとの分類結果とポイント全体のタグ。"""
    thresholds = taxonomy["thresholds"]
    shots = point.get("shots", [])
    shot_type_dim = next(d for d in taxonomy["dimensions"] if d["id"] == "shot_type")
    outcome_dim = next(d for d in taxonomy["dimensions"] if d["id"] == "outcome")

    classified_shots = []
    prev_shot_ctx: dict | None = None

    for i, shot in enumerate(shots):
        is_last = i == len(shots) - 1

        shot_type, shot_type_conf = _gated(
            shot.get("type"), shot.get("type_confidence", 0.0), shot_type_dim.get("min_confidence")
        )

        if is_last and "terminal" in shot:
            outcome, outcome_conf = _gated(
                shot["terminal"].get("type"), shot["terminal"].get("confidence", 0.0), outcome_dim.get("min_confidence")
            )
        else:
            outcome, outcome_conf = "in_play", 1.0

        shot_ctx = {"type": shot_type, "landing_depth": shot.get("landing_depth")}
        # 「直前の相手ショット」はラリー内で自分/相手が交互に打つ前提でも、実際の打者
        # 識別（誰が打ったか）を持たないため常に未解決 → forced判定は常にunforcedに倒れる
        # （不変原則1）。将来、自分/相手の打者帰属が実装され次第ここを差し替える。
        pressure_context = {
            "prev_opponent_shot": prev_shot_ctx or {},
            "shot": shot_ctx,
            "thresholds": thresholds,
        }
        pressure = _resolve_pressure(taxonomy, pressure_context)

        values = {"shot_type": shot_type, "outcome": outcome, "pressure": pressure}
        label_entry = _match_label(taxonomy, values)

        tags = []
        for tag in taxonomy.get("tags", []):
            if tag.get("scope") == "point":
                continue
            tag_context = {"shot": shot_ctx, "thresholds": thresholds}
            if evaluate_when(tag["when"], tag_context):
                tags.append(tag["id"])

        classified_shots.append(
            {
                "shot_index": shot.get("index", i),
                "shot_type": shot_type,
                "shot_type_confidence": shot_type_conf,
                "outcome": outcome,
                "outcome_confidence": outcome_conf,
                "pressure": pressure,
                "label": label_entry["label"],
                "importance": label_entry.get("importance", "none"),
                "highlight": bool(label_entry.get("highlight", False)),
                "stat_key": label_entry.get("stat_key"),
                "exclude_from_stats": bool(label_entry.get("exclude_from_stats", False)),
                "tags": tags,
            }
        )
        prev_shot_ctx = shot_ctx

    point_tags = []
    point_context = {"point": {"shot_count": point.get("shot_count", len(shots))}, "thresholds": thresholds}
    for tag in taxonomy.get("tags", []):
        if tag.get("scope") != "point":
            continue
        if evaluate_when(tag["when"], point_context):
            point_tags.append(tag["id"])

    return {"point_index": point.get("index"), "shots": classified_shots, "tags": point_tags}


def classify_event_stream(payload: dict, taxonomy: dict | None = None) -> list[dict]:
    taxonomy = taxonomy or load_taxonomy()
    return [classify_point(point, taxonomy) for point in payload.get("points", [])]
