"""週次ダイジェスト・トリガー型アドバイスの選定ロジック（07-advice-delivery.md §配信の3層設計 ②③）。

「何を言うか」（このモジュール：トリガー選定・cooldown/週内上限の適用）と
「どう言うか」（advice_llm：文面生成）を分離する（advice_engine.pyと同じ分業）。
DBアクセスを含むためadvice_engine.py（純粋関数のサンドボックス評価器）とは別モジュールにする。
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.advice import AdviceDelivery, AdviceDeliveryKind
from app.models.match import EventStream, Match, MatchStatus
from app.services.advice_engine import evaluate_triggers, load_advice_rules
from app.services.stats import compute_match_metrics

MATCH_HISTORY_LIMIT = 10

# trigger_id → その指標がmatch_metrics内のどのフィールドに対応するか。
# taxonomy_engine.pyのshot_type/outcome解決と同じ理由（イベントストリームの実データ形状に
# 直結する構造的対応）でコードに置く。しきい値・発火条件自体はYAML側（不変原則2）。
_TRIGGER_METRIC_PATH: dict[str, tuple[str, ...]] = {
    "backhand_unforced_trend": ("by_shot_type", "backhand", "unforced_error_rate"),
    "forehand_unforced_trend": ("by_shot_type", "forehand", "unforced_error_rate"),
    "serve_fault_spike": ("serve_fault_rate",),
    "double_fault_spike": ("double_faults",),
}


def _metric_value(metrics: dict, path: tuple[str, ...]) -> float | None:
    value: object = metrics
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value if isinstance(value, (int, float)) else None


def _build_match_history(db: Session, user_id) -> list[dict]:
    matches = (
        db.query(Match)
        .filter(Match.user_id == user_id, Match.status == MatchStatus.done)
        .order_by(Match.created_at)
        .all()
    )
    history = []
    for match in matches[-MATCH_HISTORY_LIMIT:]:
        stream = (
            db.query(EventStream)
            .filter(EventStream.match_id == match.id)
            .order_by(desc(EventStream.version))
            .first()
        )
        if stream is None:
            continue
        history.append(compute_match_metrics(stream.payload))
    return history


def _last_delivery_for_trigger(db: Session, user_id, trigger_id: str) -> AdviceDelivery | None:
    return (
        db.query(AdviceDelivery)
        .filter(
            AdviceDelivery.user_id == user_id,
            AdviceDelivery.kind == AdviceDeliveryKind.trigger,
            AdviceDelivery.trigger_id == trigger_id,
        )
        .order_by(desc(AdviceDelivery.created_at))
        .first()
    )


def _most_recent_delivery(db: Session, user_id) -> AdviceDelivery | None:
    return (
        db.query(AdviceDelivery)
        .filter(AdviceDelivery.user_id == user_id)
        .order_by(desc(AdviceDelivery.created_at))
        .first()
    )


def _improved_since_last_advice(db: Session, user_id, latest_metrics: dict) -> bool:
    """前回配信トリガーの指標が今回改善しているか（不変原則1: 材料が無ければFalse）。"""
    last = _most_recent_delivery(db, user_id)
    if last is None or last.kind != AdviceDeliveryKind.trigger or not last.trigger_id:
        return False
    path = _TRIGGER_METRIC_PATH.get(last.trigger_id)
    if path is None:
        return False
    before = _metric_value(last.metrics_snapshot, path)
    after = _metric_value(latest_metrics, path)
    if before is None or after is None:
        return False
    return after < before  # v1で扱う指標は全てエラー率系（低いほど良い）


def select_weekly_notifications(db: Session, user_id, rules: dict | None = None) -> dict | None:
    """今週配信する内容を選定する。試合データが無ければNone（配信しない）。

    戻り値: {"history": [...], "trigger": trigger_dict|None, "praise_fired": bool}
    """
    rules = rules or load_advice_rules()
    history = _build_match_history(db, user_id)
    if not history:
        return None

    improved = _improved_since_last_advice(db, user_id, history[-1])
    fired = evaluate_triggers(history, improved_since_last_advice=improved, rules=rules)

    praise_fired = any(t.get("standalone", True) is False for t in fired)

    max_per_week = rules["settings"]["max_trigger_notifications_per_week"]
    since = datetime.now(timezone.utc) - timedelta(days=7)
    sent_this_week = (
        db.query(AdviceDelivery)
        .filter(
            AdviceDelivery.user_id == user_id,
            AdviceDelivery.kind == AdviceDeliveryKind.trigger,
            AdviceDelivery.created_at >= since,
        )
        .count()
    )

    selected_trigger = None
    if sent_this_week < max_per_week:
        for t in fired:
            if t.get("standalone", True) is False:
                continue  # praise系は週次枠を消費しない（starvation防止、advice-rules.v1.yamlコメント）
            last_same = _last_delivery_for_trigger(db, user_id, t["id"])
            if last_same is not None:
                elapsed_days = (datetime.now(timezone.utc) - last_same.created_at).days
                if elapsed_days < t["cooldown_days"]:
                    continue
            selected_trigger = t
            break

    return {"history": history, "trigger": selected_trigger, "praise_fired": praise_fired}
