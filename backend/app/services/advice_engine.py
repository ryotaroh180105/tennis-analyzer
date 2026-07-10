"""アドバイス発火ルールエンジン（config/advice-rules.v1.yaml / 07-advice-delivery.md）。

taxonomyと同じ「evalを使わない・許可ノードのみ」のサンドボックス方針だが、
このDSLは stat()/trend()/avg()/last_match.* という名前付き関数呼び出しを持つため、
taxonomy_engineの評価器とは別に、許可された関数名のみを解決する専用の評価器を持つ。
「何を言うか」（ここで判定するトリガー）と「どう言うか」（Claude APIでの文面生成、
app/services/advice_llm.py）を分離する設計（07）。
"""

import ast
import operator
import os
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/app/config"))


@lru_cache
def load_advice_rules(version: str = "v1") -> dict:
    path = CONFIG_DIR / f"advice-rules.{version}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------
# 統計ヘルパー（純粋関数）
# ---------------------------------------------------------------


def _linear_trend(values: list[float]) -> float:
    """最小二乗法での傾き。2点未満なら0。"""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    return numerator / denominator


# ---------------------------------------------------------------
# サンドボックス評価器（関数呼び出し対応版）
# ---------------------------------------------------------------

_ALLOWED_FUNCTIONS = {"stat", "trend", "avg", "improved_since_last_advice"}

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
    ast.Call,
    ast.keyword,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Eq,
    ast.NotEq,
)

_COMPARE_OPS = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


class AdviceEvalContext:
    """triggerのwhen式が参照できるのは集計済みスタッツのみ（イベントストリーム・動画は不可、07）。

    match_history: 古い→新しい順の試合メトリクス辞書のリスト。
    """

    def __init__(self, match_history: list[dict], improved_since_last_advice: bool = False):
        self.match_history = match_history
        self._improved = improved_since_last_advice

    @property
    def last_match(self) -> dict:
        return self.match_history[-1] if self.match_history else {}

    def stat(self, shot_type: str, metric: str) -> dict:
        return {"__kind__": "stat_series", "shot_type": shot_type, "metric": metric}

    def trend(self, series: dict, matches: int) -> float:
        if not isinstance(series, dict) or series.get("__kind__") != "stat_series":
            raise ValueError("trend() expects a stat(...) series")
        window = self.match_history[-matches:]
        values = [
            m.get("by_shot_type", {}).get(series["shot_type"], {}).get(series["metric"])
            for m in window
        ]
        values = [v for v in values if v is not None]
        return _linear_trend(values)

    def avg(self, metric: str, matches: int) -> float:
        window = self.match_history[-matches:]
        values = [m.get(metric) for m in window if m.get(metric) is not None]
        return sum(values) / len(values) if values else 0.0

    def improved_since_last_advice(self) -> bool:
        return self._improved


def _eval_call(node: ast.Call, ctx: AdviceEvalContext):
    # last_match.<method>(args) — last_match は辞書アクセスなので Attribute チェーンの末尾を見る
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "last_match":
        method_name = node.func.attr
        args = [_eval_node(a, ctx) for a in node.args]
        target = ctx.last_match.get(method_name)
        if isinstance(target, dict) and len(args) == 1:
            return target.get(args[0])
        raise ValueError(f"unsupported last_match method: {method_name}")

    if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
        raise ValueError("disallowed function call in advice rule")

    fn = getattr(ctx, node.func.id)
    args = [_eval_node(a, ctx) for a in node.args]
    kwargs = {kw.arg: _eval_node(kw.value, ctx) for kw in node.keywords}
    return fn(*args, **kwargs)


def _resolve_path(node: ast.expr, ctx: AdviceEvalContext):
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.insert(0, node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        raise ValueError("unsupported expression: expected dotted field access")
    parts.insert(0, node.id)

    if parts[0] == "last_match":
        value: object = ctx.last_match
        for part in parts[1:]:
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        return value

    raise ValueError(f"unsupported identifier: {parts[0]}")


def _eval_node(node: ast.AST, ctx: AdviceEvalContext):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, ctx)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Call):
        return _eval_call(node, ctx)
    if isinstance(node, (ast.Name, ast.Attribute)):
        return _resolve_path(node, ctx)
    if isinstance(node, ast.BoolOp):
        values = [_eval_node(v, ctx) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(bool(v) for v in values)
        if isinstance(node.op, ast.Or):
            return any(bool(v) for v in values)
        raise ValueError("unsupported boolean operator")
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("chained comparisons are not supported")
        left = _eval_node(node.left, ctx)
        right = _eval_node(node.comparators[0], ctx)
        if left is None or right is None:
            return False
        op = _COMPARE_OPS.get(type(node.ops[0]))
        if op is None:
            raise ValueError("unsupported comparison operator")
        try:
            return op(left, right)
        except TypeError:
            return False
    raise ValueError(f"unsupported expression node: {type(node).__name__}")


def evaluate_when(expr: str, ctx: AdviceEvalContext) -> bool:
    tree = ast.parse(expr.strip(), mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"disallowed expression node in advice rule: {type(node).__name__}")
    return bool(_eval_node(tree, ctx))


# ---------------------------------------------------------------
# トリガー評価
# ---------------------------------------------------------------


def evaluate_triggers(
    match_history: list[dict], improved_since_last_advice: bool = False, rules: dict | None = None
) -> list[dict]:
    """発火したトリガーを priority 降順で返す。match_historyが空なら何も発火しない。"""
    rules = rules or load_advice_rules()
    if not match_history:
        return []

    ctx = AdviceEvalContext(match_history, improved_since_last_advice=improved_since_last_advice)
    fired = []
    for trigger in rules["triggers"]:
        if trigger.get("enabled", True) is False:
            continue
        try:
            if evaluate_when(trigger["when"], ctx):
                fired.append(trigger)
        except (ValueError, ZeroDivisionError):
            # 未実装の集計・データ不足による評価失敗は「発火しない」に倒す（不変原則1）
            continue

    return sorted(fired, key=lambda t: -t["priority"])
