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
        return yaml.safe_load(f)


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
